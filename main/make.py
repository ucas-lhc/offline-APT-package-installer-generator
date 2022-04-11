#!/usr/bin/python3

import pathlib, os, subprocess, shutil, shlex, stat, argparse

base_path = pathlib.Path(__file__).resolve(strict=True).parent
default_distribution_path = base_path / 'distribution'

def construct_paths():
  global repository_path, resources_path, installer_path
  repository_path = distribution_path / 'repository'
  resources_path = repository_path / 'resources'
  installer_path = distribution_path / 'install.sh'

def main():
  parse_arguments()
  construct_paths()
  resolve_dependency()
  download_packages()
  build_package_index()
  generate_installer()

def resolve_dependency():
  global full_package_list
  dependency_text = subprocess.run(
    args=[shutil.which('apt-cache'), 'depends', '--recurse', '--no-breaks',
          '--no-conflicts', '--no-replaces', '--no-recommends',
          '--no-suggests', '--no-enhances'] + package_list,
    check=True, text=True, capture_output=True,
  ).stdout
  full_package_list = list(filter(
    lambda line: line[0].isalnum(),
    dependency_text.splitlines(),
  ))

def download_packages():
  resources_path.mkdir(parents=True, exist_ok=True)
  clear_directory(resources_path)
  subprocess.run(
    args=[shutil.which('apt-get'), 'download'] + full_package_list,
    check=True, cwd=resources_path,
  )

def build_package_index():
  with (repository_path / 'Packages').open(mode='wb') as index_file:
    subprocess.run(
      args=[shutil.which('apt-ftparchive'), 'packages',
            str(resources_path.relative_to(repository_path))],
      check=True, cwd=repository_path, stdout=index_file,
    )

def generate_installer():
  installer_path.write_text(
    installer_template.replace(r'${_package_list_}', shlex.join(package_list))
  )
  installer_path.chmod(
    installer_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
  )

installer_template = r"""
#!/bin/sh

set -e #;; Exit immediately if a command exits with a non-zero status.
set -u #;; Treat unset variables as an error when substituting.

#;; locate resources
base_directory=$(dirname "$(readlink -e "${0}")")
repository_directory="${base_directory}/repository"
source_string="deb [trusted=yes] file:\"${repository_directory}\" /"

#;; temporarily change APT sources
#;;;(1) backup original APT sources directory
mv '/etc/apt/sources.list.d' '/etc/apt/sources.list.d~'
restore1(){ mv '/etc/apt/sources.list.d~' '/etc/apt/sources.list.d' ;}
panic1(){
  echo >&2 '***** PANIC: cannot restore APT sources directory *****'
  echo >&2 'Please look into backup directory "/etc/apt/sources.list.d~"'
}
failsafe1(){ restore1 || panic1 ;}
trap 'failsafe1' EXIT
#;;;(2) backup original APT sources file
mv '/etc/apt/sources.list' '/etc/apt/sources.list~'
restore2(){ mv '/etc/apt/sources.list~' '/etc/apt/sources.list' ;}
panic2(){
  echo >&2 '***** PANIC: cannot restore APT sources file *****'
  echo >&2 'Please look into backup file "/etc/apt/sources.list~"'
}
failsafe2(){ restore2 || panic2 ; failsafe1 ;}
trap 'failsafe2' EXIT
#;;;(3) update APT sources to use local repository
echo "${source_string}" >'/etc/apt/sources.list'

#;; install packages from local repository
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ${_package_list_}

#;; clear package cache
echo -n >'/etc/apt/sources.list'
apt-get update

#;; restore original APT sources
trap 'panic2 ; failsafe1' EXIT
restore2
trap 'panic1' EXIT
restore1
trap - EXIT

#;[NOTE] The original package cache is destroyed. To rebuild it, run command
#;[    ] "apt-get update" manually. The command is not executed automatically
#;[    ] because it will probably require an Internet connection.
""".lstrip()

def parse_arguments():
  global package_list, distribution_path
  parser = argparse.ArgumentParser(allow_abbrev=False)
  parser.add_argument('packages',
    nargs='+', #;; expects one or more values, stores them in a list
    help='packages to be included',
  )
  parser.add_argument('-d',
    dest='output_path',
    type=lambda string: pathlib.Path(string).resolve(),
    default=default_distribution_path,
    metavar='DIRECTORY',
    help='path to the target installer directory to be generated',
  )
  arguments = parser.parse_args()
  package_list = arguments.packages
  distribution_path = arguments.output_path

def clear_directory(path):
  for _, dirnames, filenames, dirfd in os.fwalk(top=path, topdown=False):
    for filename in filenames:
      os.remove(path=filename, dir_fd=dirfd)
    for dirname in dirnames:
      os.rmdir(path=dirname, dir_fd=dirfd)

if __name__ == '__main__':
  main()
