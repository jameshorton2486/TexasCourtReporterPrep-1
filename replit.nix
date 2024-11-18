{pkgs}: {
  deps = [
    pkgs.nodePackages.prettier
    pkgs.glibcLocales
    pkgs.file
    pkgs.openssl
    pkgs.postgresql
  ];
}
