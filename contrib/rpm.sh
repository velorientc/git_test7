#!/bin/sh

mkdir -p rpmbuild/{SOURCES,BUILD,RPMS,SRPMS,SPECS}
version=`hg parents --template '{latesttag}+{latesttagdistance}'`
if [ `expr "$version" : '.*+0$'` -ne 0 ]; then
  # We are on a tagged version
  version=`expr "$version" : '\(.*\)+0$'`
  release='1'
else
  release=`hg parents --template '{node|short}'`
fi

hg archive -t tgz rpmbuild/SOURCES/tortoisehg-$version.tar.gz
sed -e "s,^Version:.*,Version: $version," \
    -e "s,^Release:.*,Release: $release," \
    `dirname $0`/tortoisehg.spec > rpmbuild/SPECS/tortoisehg.spec

rpmbuild --define "_topdir `pwd`/rpmbuild" -ba rpmbuild/SPECS/tortoisehg.spec || exit 1
rm -rf rpmbuild/BUILD/
ls -l rpmbuild/{RPMS/*,SRPMS}/tortoisehg-*.rpm
