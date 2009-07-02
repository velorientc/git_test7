#!/bin/sh

mkdir -p rpmbuild/{SOURCES,BUILD}
hg archive -t tgz rpmbuild/SOURCES/tortoisehg-hg.tar.gz
rpmbuild --define "_topdir $(pwd)/rpmbuild" -ba $(dirname $0)/tortoisehg.spec
rm -rf rpmbuild/BUILD/
ls -l rpmbuild/{RPMS/*,SRPMS}/tortoisehg-*.rpm
