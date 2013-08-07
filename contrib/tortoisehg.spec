%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

Name:       tortoisehg
Version:    hg
Release:    hg
Summary:    Mercurial GUI command line tool thg
Group:      Development/Tools
License:    GPLv2
# Few files are under the more permissive GPLv2+
URL:        http://tortoisehg.org
Source0:    %{name}-%{version}.tar.gz
BuildRoot:  %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch:  noarch
BuildRequires:  python, python-devel, gettext, python-sphinx
BuildRequires:  PyQt4-devel, desktop-file-utils
Requires:   python >= 2.4, python-iniparse, mercurial >= 2.6
# gconf needed at util/shlib.py for browse_url(url).
Requires:   gnome-python2-gconf
Requires:   PyQt4 >= 4.6, qscintilla-python, python-pygments

%description
This package contains the thg command line tool which provides a
graphical user interface to the Mercurial distributed revision control system.

%package    nautilus
Summary:    Mercurial GUI plug-in to the Nautilus file manager
Group:      Development/Tools
Requires:   %{name} = %{version}-%{release}, nautilus-python

%description    nautilus
This package contains the TortoiseHg Gnome/Nautilus extension,
which makes the Mercurial distributed revision control
system available in the file manager with a graphical interface.

%prep
%setup -q

cat > tortoisehg/util/config.py << EOT
bin_path     = "%{_bindir}"
license_path = "%{_docdir}/%{name}-%{version}/COPYING.txt"
locale_path  = "%{_datadir}/locale"
icon_path    = "%{_datadir}/pixmaps/tortoisehg/icons"
nofork       = True
EOT

%build
%{__python} setup.py build

(cd doc && make html)
rm -f doc/build/html/.buildinfo

%install
rm -rf $RPM_BUILD_ROOT

%{__python} setup.py install -O1 --skip-build --root $RPM_BUILD_ROOT

mkdir -p $RPM_BUILD_ROOT/%{_sysconfdir}/mercurial/hgrc.d
install contrib/mergetools.rc $RPM_BUILD_ROOT%{_sysconfdir}/mercurial/hgrc.d/thgmergetools.rc

ln -s tortoisehg/icons/svg/thg_logo.svg %{buildroot}%{_datadir}/pixmaps/thg_logo.svg
desktop-file-install --dir=%{buildroot}%{_datadir}/applications contrib/%{name}.desktop

%find_lang %{name}

%clean
rm -rf $RPM_BUILD_ROOT

%files -f %{name}.lang

%defattr(-,root,root,-)
%doc COPYING.txt doc/build/html/
%{_bindir}/thg
%{python_sitelib}/tortoisehg/
%if "%{?python_version}" > "2.4"
%{python_sitelib}/tortoisehg-*.egg-info
%endif
%{_datadir}/pixmaps/tortoisehg/
%{_datadir}/pixmaps/thg_logo.svg
%{_datadir}/applications/%{name}.desktop

%config(noreplace) %attr(644,root,root) %{_sysconfdir}/mercurial/hgrc.d/thgmergetools.rc

%files nautilus
%defattr(-,root,root,-)
%{_datadir}/nautilus-python/extensions/nautilus-thg.py*

%changelog
