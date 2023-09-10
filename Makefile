PREFIX = /usr/local
BINDIR = $(PREFIX)/bin
MANDIR = $(PREFIX)/share/man/man1
DOCDIR = $(PREFIX)/share/doc/nrrdtime
BSHDIR = /etc/bash_completion.d

.PHONY: all install uninstall

all:

install:
	install -m755 -d $(BINDIR)
	install -m755 -d $(MANDIR)
	install -m755 -d $(DOCDIR)
	install -m755 -d $(BSHDIR)
	gzip -c doc/nrrdtime.1 > nrrdtime.1.gz
	install -m755 nrrdtime/nrrdtime.py $(BINDIR)/nrrdtime
	install -m644 nrrdtime.1.gz $(MANDIR)
	install -m644 README.md $(DOCDIR)
	install -m644 LICENSE $(DOCDIR)
	install -m644 CHANGES $(DOCDIR)
	install -m644 CONTRIBUTING.md $(DOCDIR)
	install -m644 auto-completion/bash/nrrdtime-completion.bash $(BSHDIR)
	rm -f nrrdtime.1.gz

uninstall:
	rm -f $(BINDIR)/nrrdtime
	rm -f $(MANDIR)/nrrdtime.1.gz
	rm -f $(BSHDIR)/nrrdtime-completion.bash
	rm -rf $(DOCDIR)

