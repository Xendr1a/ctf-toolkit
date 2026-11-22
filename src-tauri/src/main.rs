// CTF Toolkit 桌面壳。界面仍是 web/（从后端回环端口加载），壳只负责：
// 起 Python 后端子进程 → 从 stdout 读真实端口 → 开原生窗口 → 退出时回收后端。
use std::io::{BufRead, BufReader};
use std::os::fd::AsRawFd;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc;
use std::sync::Mutex;
use std::time::Duration;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

struct Backend(Mutex<Option<Child>>);

static EXITING: AtomicBool = AtomicBool::new(false);
static GOT_SIGNAL: AtomicBool = AtomicBool::new(false);

extern "C" fn on_signal(_sig: libc::c_int) {
    GOT_SIGNAL.store(true, Ordering::SeqCst); // 信号处理里只做原子写，退出交给 watcher 线程
}

/// 单实例锁：flock 排它锁，拿到就返回 File（进程活着期间持有），拿不到返回 None。
/// 进程退出/崩溃时内核自动释放锁，不会有 PID 文件那种僵尸锁。
fn acquire_single_instance_lock() -> Option<std::fs::File> {
    let uid = unsafe { libc::getuid() };
    let path = std::env::temp_dir().join(format!("ctf-toolkit-{uid}.lock"));
    let file = std::fs::OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(false)
        .open(path)
        .ok()?;
    let ret = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
    if ret != 0 {
        return None;
    }
    Some(file)
}

fn repo_root() -> PathBuf {
    if let Ok(p) = std::env::var("TOOLKIT_ROOT") {
        return PathBuf::from(p);
    }
    // 安装布局：二进制放在仓库里/旁时向上找 tools.toml
    if let Ok(exe) = std::env::current_exe() {
        for anc in exe.ancestors().skip(1) {
            if anc.join("tools.toml").is_file() {
                return anc.to_path_buf();
            }
        }
    }
    // 兜底：编译期仓库根（本机开发/安装场景）
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("src-tauri 必须在仓库内")
        .to_path_buf()
}

fn stop_backend(child: &mut Child) {
    // SIGTERM 让后端走正常退出路径（它会杀各工具进程组）；3s 不退再 SIGKILL
    unsafe { libc::kill(child.id() as libc::pid_t, libc::SIGTERM) };
    for _ in 0..30 {
        if let Ok(Some(_)) = child.try_wait() {
            return;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    let _ = child.kill();
    let _ = child.wait();
}

fn main() {
    // 单实例锁：已经有实例在跑就直接退出，避免起两个后端两个窗口
    let _lock = match acquire_single_instance_lock() {
        Some(f) => f,
        None => {
            eprintln!("ctf-toolkit 已在运行（单实例锁）");
            std::process::exit(0);
        }
    };

    let root = repo_root();
    let script = root.join("toolkit.py");
    if !script.is_file() {
        eprintln!("找不到 toolkit.py：设 TOOLKIT_ROOT 指向仓库根");
        std::process::exit(1);
    }
    let mut child = match Command::new("python3")
        .arg(&script)
        .arg("--no-browser")
        .arg("--port")
        .arg("0")
        .current_dir(&root)
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
    {
        Ok(c) => c,
        Err(e) => {
            eprintln!("启动 python3 后端失败: {e}");
            std::process::exit(1);
        }
    };

    let (tx_url, rx_url) = mpsc::channel::<String>();
    let (tx_dead, rx_dead) = mpsc::channel::<()>();
    let stdout = child.stdout.take().expect("piped stdout");
    std::thread::spawn(move || {
        let mut got_url = false;
        for line in BufReader::new(stdout).lines() {
            let Ok(line) = line else { break };
            if !got_url {
                if let Some(pos) = line.find("http://127.0.0.1:") {
                    let url = line[pos..]
                        .split_whitespace()
                        .next()
                        .unwrap_or("")
                        .to_string();
                    if !url.is_empty() {
                        got_url = true;
                        let _ = tx_url.send(url);
                    }
                }
            }
        }
        if got_url {
            let _ = tx_dead.send(()); // stdout 关闭 = 后端进程已退出
        }
    });

    let url = match rx_url.recv_timeout(Duration::from_secs(20)) {
        Ok(u) => u,
        Err(_) => {
            eprintln!("后端 20s 内没报出端口（python 报错见上方 stderr）");
            stop_backend(&mut child);
            std::process::exit(1);
        }
    };

    // Ctrl-C / kill 也要走正常退出回收后端，不能留孤儿
    unsafe {
        libc::signal(
            libc::SIGTERM,
            on_signal as extern "C" fn(libc::c_int) as usize,
        );
        libc::signal(
            libc::SIGINT,
            on_signal as extern "C" fn(libc::c_int) as usize,
        );
    }

    tauri::Builder::default()
        .manage(Backend(Mutex::new(Some(child))))
        .setup(move |app| {
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                // 后端自己死了就关窗，不留空壳；我们主动回收时不触发
                if rx_dead.recv().is_ok() && !EXITING.load(Ordering::SeqCst) {
                    handle.exit(0);
                }
            });
            let handle2 = app.handle().clone();
            std::thread::spawn(move || loop {
                if GOT_SIGNAL.load(Ordering::SeqCst) {
                    handle2.exit(0);
                    break;
                }
                std::thread::sleep(Duration::from_millis(100));
            });
            WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::External(url.parse().expect("后端 URL 合法")),
            )
            .title("CTF Toolkit")
            .inner_size(1440.0, 900.0)
            .min_inner_size(960.0, 600.0)
            .center()
            .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("构建 Tauri 应用失败")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                EXITING.store(true, Ordering::SeqCst);
                if let Some(mut c) = app.state::<Backend>().0.lock().unwrap().take() {
                    stop_backend(&mut c);
                }
            }
        });
}
