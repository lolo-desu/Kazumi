{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  packages = [ (pkgs.python3.withPackages (p: [ p.pygobject3 p.pycairo ]))
    pkgs.gobject-introspection pkgs.gtk4 pkgs.libadwaita pkgs.webkitgtk_6_0
    pkgs.mpv pkgs.ffmpeg pkgs.libsecret pkgs.qrencode pkgs.dart pkgs.steam-run-free ];
  shellHook = ''
    export NATIVE_IN_SHELL=1
    export NATIVE_CORE_RUNNER=steam-run
    export NATIVE_MPV_LIBRARY=${pkgs.mpv}/lib/libmpv.so
    export NATIVE_EGL_LIBRARY=${pkgs.libglvnd}/lib/libEGL.so
    export LD_LIBRARY_PATH=/run/opengl-driver/lib:$LD_LIBRARY_PATH
  '';
}
