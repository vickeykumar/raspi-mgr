include Makefile.include
DEBIAN_ROOT = ${ROOT}/deb

deb:
	mkdir -p ${DEBIAN_ROOT}/raspi-mgr/usr/lib/systemd/system
	mkdir -p ${DEBIAN_ROOT}/raspi-mgr/usr/local/scripts/
	install -m 644 ${ROOT}/src/raspi-mgr.service ${DEBIAN_ROOT}/raspi-mgr/usr/lib/systemd/system/raspi-mgr.service
	install -m 755 ${ROOT}/src/raspi_mgr.py ${DEBIAN_ROOT}/raspi-mgr/usr/local/scripts/raspi_mgr.py
	cd ${DEBIAN_ROOT} && dpkg-deb --build raspi-mgr/
