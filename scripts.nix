{ pkgs }: with pkgs; {
  firmware = {
    ci = writeScriptBin "firmware-ci" ''
      set -e
      cd firmware

      echo "::group::Checking Python with ruff"
      ruff check .
      echo "::endgroup::"
    '';
  };
}
