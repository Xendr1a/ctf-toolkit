<?php
// 仅供本地自测用的靶页（SQL 注入 / 目录枚举）。不要放到公网。
header('Content-Type: application/json; charset=utf-8');
$db = new PDO('sqlite::memory:');
$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$db->exec("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT)");
$db->exec("INSERT INTO users (username,password) VALUES ('admin','flag{local_demo_only}'),('guest','guest')");

$id = $_GET['id'] ?? '1';
$sql = "SELECT * FROM users WHERE id = $id";   // 故意拼接
try {
    $rows = $db->query($sql)->fetchAll(PDO::FETCH_ASSOC);
    echo json_encode(['query' => $sql, 'rows' => $rows], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['error' => $e->getMessage(), 'query' => $sql], JSON_UNESCAPED_UNICODE);
}
