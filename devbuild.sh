#!/bin/bash

# usage instructions
usage () {
cat << EOF_USAGE
Usage: $0 --platform=PLATFORM [OPTIONS]...

OPTIONS
  -h, --help
      show this help guide
  -p, --platform=PLATFORM
      name of machine you are building on
      (e.g. cheyenne | hera | jet | orion | wcoss_dell_p3)
  -c, --compiler=COMPILER
      compiler to use; default depends on platform
      (e.g. intel | gnu | cray | gccgfortran)
  -a, --app=APPLICATION
      weather model application to build; for example, ATMAQ for RRFS-CMAQ
      (e.g. ATM | ATMAQ | ATMW | S2S | S2SW)
  -e, --extrn=EXTERNALS
      check out external components (YES | NO)
  --ccpp="CCPP_SUITE1,CCPP_SUITE2..."
      CCPP suites (CCCP_SUITES) to include in build; delimited with ','
  --enable-options="OPTION1,OPTION2,..."
      enable ufs-weather-model options; delimited with ','
      (e.g. 32BIT | INLINE_POST | UFS_GOCART | MOM6 | CICE6 | WW3 | CMEPS)
  --disable-options="OPTION1,OPTION2,..."
      disable ufs-weather-model options; delimited with ','
      (e.g. 32BIT | INLINE_POST | UFS_GOCART | MOM6 | CICE6 | WW3 | CMEPS)
  --continue
      continue with existing build
  --clean
      removes existing build; overrides --continue
  --build-dir=BUILD_DIR
      build directory
  --install-dir=INSTALL_DIR
      installation prefix
  --build-type=BUILD_TYPE
      build type; defaults to RELEASE
      (e.g. DEBUG | RELEASE | RELWITHDEBINFO)
  --build-jobs=BUILD_JOBS
      number of build jobs; defaults to 4
  -v, --verbose
      build with verbose output

NOTE: This script is for internal developer use only;
See User's Guide for detailed build instructions

EOF_USAGE
}

# print settings
settings () {
cat << EOF_SETTINGS
Settings:

  SRW_DIR=${SRW_DIR}
  BIN_DIR=${BIN_DIR}
  BUILD_DIR=${BUILD_DIR}
  INSTALL_DIR=${INSTALL_DIR}
  PLATFORM=${PLATFORM}
  COMPILER=${COMPILER}
  APP=${APPLICATION}
  EXTRN=${EXTERNALS}
  CCPP=${CCPP_SUITES}
  ENABLE_OPTIONS=${ENABLE_OPTIONS}
  DISABLE_OPTIONS=${DISABLE_OPTIONS}
  CLEAN=${CLEAN}
  CONTINUE=${CONTINUE}
  BUILD_TYPE=${BUILD_TYPE}
  BUILD_JOBS=${BUILD_JOBS}
  VERBOSE=${VERBOSE}

EOF_SETTINGS
}

# print usage error and exit
usage_error () {
  printf "ERROR: $1\n" >&2
  usage >&2
  exit 1
}

# default settings
LCL_PID=$$
SRW_DIR=$(cd "$(dirname "$(readlink -f -n "${BASH_SOURCE[0]}" )" )" && pwd -P)
BIN_DIR="${SRW_DIR}/bin"
MACHINE_SETUP=${SRW_DIR}/src/UFS_UTILS/sorc/machine-setup.sh
BUILD_DIR="${SRW_DIR}/build"
INSTALL_DIR=${SRW_DIR}
COMPILER=""
APPLICATION=""
EXTERNALS="NO"
CCPP_SUITES=""
ENABLE_OPTIONS=""
DISABLE_OPTIONS=""
BUILD_TYPE="RELEASE"
BUILD_JOBS=4
CLEAN=false
CONTINUE=false
VERBOSE=false

# process required arguments
if [[ ("$1" == "--help") || ("$1" == "-h") ]]; then
  usage
  exit 0
fi

# process optional arguments
while :; do
  case $1 in
    --help|-h) usage; exit 0 ;;
    --platform=?*|-p=?*) PLATFORM=${1#*=} ;;
    --platform|--platform=|-p|-p=) usage_error "$1 requires argument." ;;
    --compiler=?*|-c=?*) COMPILER=${1#*=} ;;
    --compiler|--compiler=|-c|-c=) usage_error "$1 requires argument." ;;
    --app=?*|-a=?*) APPLICATION=${1#*=} ;;
    --app|--app=|-a|-a=) usage_error "$1 requires argument." ;;
    --extrn=?*|-e=?*) EXTERNALS=${1#*=} ;;
    --extrn|--extrn=|-e|-e=) usage_error "$1 requires argument." ;;
    --ccpp=?*) CCPP_SUITES=${1#*=} ;;
    --ccpp|--ccpp=) usage_error "$1 requires argument." ;;
    --enable-options=?*) ENABLE_OPTIONS=${1#*=} ;;
    --enable-options|--enable-options=) usage_error "$1 requires argument." ;;
    --disable-options=?*) DISABLE_OPTIONS=${1#*=} ;;
    --disable-options|--disable-options=) usage_error "$1 requires argument." ;;
    --clean) CLEAN=true ;;
    --clean=?*|--clean=) usage_error "$1 argument ignored." ;;
    --continue) CONTINUE=true ;;
    --continue=?*|--continue=) usage_error "$1 argument ignored." ;;
    --build-dir=?*) BUILD_DIR=${1#*=} ;;
    --build-dir|--build-dir=) usage_error "$1 requires argument." ;;
    --install-dir=?*) INSTALL_DIR=${1#*=} ;;
    --install-dir|--install-dir=) usage_error "$1 requires argument." ;;
    --build-type=?*) BUILD_TYPE=${1#*=} ;;
    --build-type|--build-type=) usage_error "$1 requires argument." ;;
    --build-jobs=?*) BUILD_JOBS=$((${1#*=})) ;;
    --build-jobs|--build-jobs=) usage_error "$1 requires argument." ;;
    --verbose|-v) VERBOSE=true ;;
    --verbose=?*|--verbose=) usage_error "$1 argument ignored." ;;
    -?*|?*) usage_error "Unknown option $1" ;;
    *) break
  esac
  shift
done

# Ensure uppercase / lowercase ============================================
APPLICATION="${APPLICATION^^}"
PLATFORM="${PLATFORM,,}"
COMPILER="${COMPILER,,}"
EXTERNALS="${EXTERNALS^^}"

# check if PLATFORM is set
if [ -z $PLATFORM ] ; then
  printf "\nERROR: Please set PLATFORM.\n\n"
  usage
  exit 0
fi

# set PLATFORM (MACHINE)
MACHINE="${PLATFORM}"
printf "PLATFORM(MACHINE)=${PLATFORM}\n" >&2

set -eu

# automatically determine compiler
if [ -z "${COMPILER}" ] ; then
  case ${PLATFORM} in
    jet|hera|gaea) COMPILER=intel ;;
    orion) COMPILER=intel ;;
    wcoss_dell_p3) COMPILER=intel ;;
    cheyenne) COMPILER=intel ;;
    macos,singularity) COMPILER=gnu ;;
    odin) COMPILER=intel ;;
    *)
      COMPILER=intel
      printf "WARNING: Setting default COMPILER=intel for new platform ${PLATFORM}\n" >&2;
      ;;
  esac
fi

printf "COMPILER=${COMPILER}\n" >&2

# print settings
if [ "${VERBOSE}" = true ] ; then
  settings
fi

# Check out external components ===========================================
if [ "${EXTERNALS}" = "YES" ]; then
  printf "... Checking out the external components ...\n"
  ./manage_externals/checkout_externals
  if [ "${APPLICATION}" = "ATMAQ" ]; then
    printf "... Replace regional workflow with the one for RRFS-CMAQ ...\n"
    rm -rf regional_workflow
    printf "... Checking out additional external components for RRFS-CMAQ ...\n"
    ./manage_externals/checkout_externals -e externals/Externals_AQM.cfg
  fi
fi

# set MODULE_FILE for this platform/compiler combination
MODULE_FILE="build_${PLATFORM}_${COMPILER}"
if [ ! -f "${SRW_DIR}/modulefiles/${MODULE_FILE}" ]; then
  printf "ERROR: module file does not exist for platform/compiler\n" >&2
  printf "  MODULE_FILE=${MODULE_FILE}\n" >&2
  printf "  PLATFORM=${PLATFORM}\n" >&2
  printf "  COMPILER=${COMPILER}\n\n" >&2
  printf "Please make sure PLATFORM and COMPILER are set correctly\n" >&2
  usage >&2
  exit 64
fi

printf "MODULE_FILE=${MODULE_FILE}\n" >&2

# if build directory already exists then exit
if [ "${CLEAN}" = true ]; then
  printf "Remove build directory\n"
  printf "  BUILD_DIR=${BUILD_DIR}\n\n"
  rm -rf ${BUILD_DIR}
elif [ "${CONTINUE}" = true ]; then
  printf "Continue build in directory\n"
  printf "  BUILD_DIR=${BUILD_DIR}\n\n"
else
  if [ -d "${BUILD_DIR}" ]; then
    while true; do
      if [[ $(ps -o stat= -p ${LCL_PID}) != *"+"* ]] ; then
        printf "ERROR: Build directory already exists\n" >&2
        printf "  BUILD_DIR=${BUILD_DIR}\n\n" >&2
        usage >&2
        exit 64
      fi
      # interactive selection
      printf "Build directory (${BUILD_DIR}) already exists\n"
      printf "Please choose what to do:\n\n"
      printf "[R]emove the existing directory\n"
      printf "[C]ontinue building in the existing directory\n"
      printf "[Q]uit this build script\n"
      read -p "Choose an option (R/C/Q):" choice
      case ${choice} in
        [Rr]* ) rm -rf ${BUILD_DIR}; break ;;
        [Cc]* ) break ;;
        [Qq]* ) exit ;;
        * ) printf "Invalid option selected.\n" ;;
      esac
    done
  fi
fi

# cmake settings
CMAKE_SETTINGS="-DCMAKE_INSTALL_PREFIX=${INSTALL_DIR}"
CMAKE_SETTINGS="${CMAKE_SETTINGS} -DCMAKE_BUILD_TYPE=${BUILD_TYPE}"
if [ ! -z "${APPLICATION}" ]; then
  CMAKE_SETTINGS="${CMAKE_SETTINGS} -DAPP=${APPLICATION}"
fi
if [ ! -z "${CCPP_SUITES}" ]; then
  CMAKE_SETTINGS="${CMAKE_SETTINGS} -DCCPP_SUITES=${CCPP_SUITES}"
fi
if [ ! -z "${ENABLE_OPTIONS}" ]; then
  CMAKE_SETTINGS="${CMAKE_SETTINGS} -DENABLE_OPTIONS=${ENABLE_OPTIONS}"
fi
if [ ! -z "${DISABLE_OPTIONS}" ]; then
  CMAKE_SETTINGS="${CMAKE_SETTINGS} -DDISABLE_OPTIONS=${DISABLE_OPTIONS}"
fi
if [ "${APPLICATION}" = "ATMAQ" ]; then
  CMAKE_SETTINGS="${CMAKE_SETTINGS} -DCPL_AQM=ON"
fi

# make settings
MAKE_SETTINGS="-j ${BUILD_JOBS}"
if [ "${VERBOSE}" = true ]; then
  MAKE_SETTINGS="${MAKE_SETTINGS} VERBOSE=1"
fi

# Before we go on load modules, we first need to activate Lmod for some systems
source ${SRW_DIR}/etc/lmod-setup.sh

# source the module file for this platform/compiler combination, then build the code
printf "... Load MODULE_FILE and create BUILD directory ...\n"
module use ${SRW_DIR}/modulefiles
module load ${MODULE_FILE}
module list
mkdir -p ${BUILD_DIR}
cd ${BUILD_DIR}
printf "... Generate CMAKE configuration ...\n"
cmake ${SRW_DIR} ${CMAKE_SETTINGS} 2>&1 | tee log.cmake
printf "... Compile executables ...\n"
make ${MAKE_SETTINGS} 2>&1 | tee log.make


## Checking executables in BIN_DIR ========================================

# Output file name to check executables ===================================
BUILD_OUT_FN="build_exec_pass.out"

### List of Excutables ### ================================================
# Basic executables of the UFS SRW App ====================================
declare -a exec_srw=( chgres_cube \
                      emcsfc_ice_blend \
                      emcsfc_snow2mdl \
                      filter_topo \
                      fregrid \
                      fvcom_to_FV3 \
                      global_cycle \
                      global_equiv_resol \
                      inland \
                      lakefrac \
                      make_hgrid \
                      make_solo_mosaic \
                      orog \
                      orog_gsl \
                      regional_esg_grid \
                      sfc_climo_gen \
                      shave \
                      ufs_model \
                      upp.x \
                      vcoord_gen )
## Additional executables for ATMAQ =======================================
declare -a exec_aqm=( nexus \
                      gefs2lbc_para )
### List end ### ==========================================================

cd ${SRW_DIR}

printf "... Checking executables in bin ...\n"
# Create output file to check if executables exist in BIN_DIR =============
if [ ! -f "${BUILD_OUT_FN}" ]; then
   touch ${BUILD_OUT_FN}
fi
# Check if all executables exist in BIN_DIR ===============================
n_fail=0
echo $( date --utc ) >> ${BUILD_OUT_FN}
for file in "${exec_srw[@]}" ; do
  exec_file="${BIN_DIR}/${file}"
  if [ -f ${exec_file} ]; then
    echo "PASS:: executable = ${file}" >> ${BUILD_OUT_FN}
  else
    echo "FAIL:: executable = ${file}" >> ${BUILD_OUT_FN}
    (( n_fail=n_fail+1 ))
  fi
done
if [ "${APPLICATION}" = "ATMAQ" ]; then
  for file in "${exec_aqm[@]}" ; do
    exec_file="${BIN_DIR}/${file}"
    if [ -f ${exec_file} ]; then
      echo "PASS:: executable = ${file}" >> ${BUILD_OUT_FN}
    else
      echo "FAIL:: executable = ${file}" >> ${BUILD_OUT_FN}
      (( n_fail=n_fail+1 ))
    fi
  done
fi

echo "... Check the build result file: ${BUILD_OUT_FN} ..."
if [ ${n_fail} -eq 0 ]; then
  echo "===== App-build: COMPLETED !!! ====="
else
  echo "===== App-build: FAILED !!! ====="
  echo "===== Number of failed executables:" ${n_fail}
  echo "===== Please check:" ${BUILD_OUT_FN}
fi


exit 0
