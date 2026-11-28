/* {{NAME}} —— Pwn 骨架。替换成真实漏洞；FLAG 只从环境变量读。 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *flag_value(void) {
    const char *f = getenv("GZCTF_FLAG");
    if (!f || !*f) f = getenv("FLAG");
    return (f && *f) ? f : "flag{unset}";
}

int main(void) {
    char line[128];
    puts("=== {{NAME}} ===");
    puts("input the password:");
    fflush(stdout);

    if (!fgets(line, sizeof line, stdin)) return 1;
    line[strcspn(line, "\r\n")] = '\0';

    if (strcmp(line, "{{NAME}}") == 0) {
        printf("%s\n", flag_value());
        return 0;
    }
    puts("wrong");
    return 1;
}
