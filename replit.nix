{pkgs}: {
  deps = [
    pkgs.rustc
    pkgs.libiconv
    pkgs.cargo
    pkgs.nodePackages.prettier
    pkgs.glibcLocales
    pkgs.file
    pkgs.openssl
    pkgs.postgresql
  ];
}
