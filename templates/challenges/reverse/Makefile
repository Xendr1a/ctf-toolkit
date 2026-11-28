CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra

dist/chall: src/chall.c
	@mkdir -p dist
	$(CC) $(CFLAGS) -s -o $@ $<

clean:
	rm -rf dist

.PHONY: clean
