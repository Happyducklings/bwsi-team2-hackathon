#include <stdio.h>
#include <string.h>

int main(void) {
    char buf[64];
    printf("Enter the flag: ");
    if (!fgets(buf, sizeof buf, stdin)) return 1;
    buf[strcspn(buf, "\n")] = 0;

    if (strcmp(buf, "R3v3rs3d_5ucc3ss") == 0)
        puts("Correct!");
    else
        puts("Nope.");
    return 0;
}