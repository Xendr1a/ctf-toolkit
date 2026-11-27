/* {{NAME}} —— Reverse 骨架：逆出口令后向服务提交，二进制本身不含 flag。 */
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    const char *password = "{{NAME}}-r3v";

    if (argc != 2) {
        printf("usage: %s <password>\n", argv[0]);
        return 1;
    }
    if (strcmp(argv[1], password) == 0) {
        puts("correct. submit it to /flag?password=<password> on the service.");
        return 0;
    }
    puts("wrong");
    return 1;
}
