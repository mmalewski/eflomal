CFLAGS=-Ofast -march=native -Wall --std=gnu99 -Wno-unused-function -g -fopenmp
# This is more suitable for debugging:
#CFLAGS=-Og -Wall --std=gnu99 -Wno-unused-function -g -fopenmp
LDFLAGS=-lm -lrt -lgomp -fopenmp
INSTALLDIR=/usr/local/bin

all: eflomal

eflomal.o: eflomal.c natmap.c hash.c random.c simd_math_prims.h
	$(CC) $(CFLAGS) -c eflomal.c

eflomal: eflomal.o

install: eflomal
	install -t $(INSTALLDIR) eflomal

clean:
	rm -f eflomal eflomal.o

