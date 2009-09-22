%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
# Pure python package
%define debug_package %{nil} 

Name:		tortoisehg
Version:	hg
Release:	hg
Summary:	Mercurial GUI command line tool hgtk
Group:		Development/Tools
License:	GPLv2
URL:		http://bitbucket.org/tortoisehg/stable/wiki/
Source0:	tortoisehg-%{version}.tar.gz
BuildRoot:	%{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildRequires:	python, python-devel, gettext, python-sphinx
Requires:	python >= 2.4, python-iniparse, mercurial >= 1.3, gnome-python2-gconf
Requires:	gnome-python2-gtksourceview, pycairo, pygobject2, pygtk2 >= 2.10

%description
This package contains the hgtk command line tool which provides a 
graphical user interface to the Mercurial distributed revision control system. 

%package	nautilus
Summary:	Mercurial GUI plugin to Nautilus file manager 
Group:		Development/Tools
Requires:	%{name} = %{version}-%{release}, nautilus-python

%description	nautilus
This package contains the TortoiseHg Gnome/Nautilus extension,
which makes the Mercurial distributed revision control 
system available in the file manager with a graphical interface. 

%prep
%setup -q

# Fix for nautilus python extensions in lib64 on x86_64
sed -i "s,lib/nautilus,%{_lib}/nautilus,g" setup.py

cat > tortoisehg/util/config.py << EOT
bin_path     = "%{_bindir}"
license_path = "%{_docdir}/%{name}-%{version}/COPYING.txt"
locale_path  = "%{_datadir}/locale"
icon_path    = "%{_datadir}/pixmaps/tortoisehg/icons"
EOT

%build
%{__python} setup.py build

cd doc
make html

%install
rm -rf $RPM_BUILD_ROOT

%{__python} setup.py install -O1 --skip-build --root $RPM_BUILD_ROOT

install -m 644 -D contrib/_hgtk $RPM_BUILD_ROOT/%{_datadir}/zsh/site-functions/_hgtk

%clean
rm -rf $RPM_BUILD_ROOT

%files
%defattr(-,root,root,-)
%doc COPYING.txt ReleaseNotes.txt doc/build/html/
%{_bindir}/hgtk
%{python_sitelib}/tortoisehg/hgtk/
%{python_sitelib}/tortoisehg/util/
%{python_sitelib}/tortoisehg-*.egg-info
%{_datadir}/pixmaps/tortoisehg/
%{_datadir}/locale/*/LC_MESSAGES/tortoisehg.mo
# /usr/share/zsh/site-functions/ is owned by zsh package which we don't want to
# require. We also don't want to create a sub-package just for this dependency.
# Instead we just claim ownership of the zsh top folder ...
%{_datadir}/zsh

%files nautilus
%defattr(-,root,root,-)
%{_libdir}/nautilus/extensions-2.0/python/nautilus-thg.py*

%changelog
