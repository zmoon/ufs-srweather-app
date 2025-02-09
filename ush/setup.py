#!/usr/bin/env python3

import os
import sys
import datetime
import traceback
import logging
from textwrap import dedent

from python_utils import (
    log_info,
    cd_vrfy,
    mkdir_vrfy,
    rm_vrfy,
    check_var_valid_value,
    lowercase,
    uppercase,
    list_to_str,
    check_for_preexist_dir_file,
    flatten_dict,
    check_structure_dict,
    update_dict,
    import_vars,
    get_env_var,
    load_config_file,
    cfg_to_shell_str,
    cfg_to_yaml_str,
    load_ini_config,
    get_ini_value,
    str_to_list,
    extend_yaml,
)

from set_cycle_dates import set_cycle_dates
from set_predef_grid_params import set_predef_grid_params
from set_ozone_param import set_ozone_param
from set_gridparams_ESGgrid import set_gridparams_ESGgrid
from set_gridparams_GFDLgrid import set_gridparams_GFDLgrid
from link_fix import link_fix
from check_ruc_lsm import check_ruc_lsm
from set_thompson_mp_fix_files import set_thompson_mp_fix_files


def load_config_for_setup(ushdir, default_config, user_config):
    """Load in the default, machine, and user configuration files into
    Python dictionaries. Return the combined experiment dictionary.

    Args:
      ushdir             (str): Path to the ush directory for SRW
      default_config     (str): Path to the default config YAML
      user_config        (str): Path to the user-provided config YAML

    Returns:
      Python dict of configuration settings from YAML files.
    """

    # Load the default config.
    logging.debug(f"Loading config defaults file {default_config}")
    cfg_d = load_config_file(default_config)
    logging.debug(f"Read in the following values from config defaults file:\n")
    logging.debug(cfg_d)

    # Load the user config file, then ensure all user-specified
    # variables correspond to a default value.
    if not os.path.exists(user_config):
        raise FileNotFoundError(
            f"""
            User config file not found:
            user_config = {user_config}
            """
        )

    try:
        cfg_u = load_config_file(user_config)
        logging.debug(f"Read in the following values from YAML config file {user_config}:\n")
        logging.debug(cfg_u)
    except:
        errmsg = dedent(
            f"""\n
            Could not load YAML config file:  {user_config}
            Reference the above traceback for more information.
            """
        )
        raise Exception(errmsg)

    # Make sure the keys in user config match those in the default
    # config.
    invalid = check_structure_dict(cfg_u, cfg_d)
    if invalid:
        errmsg = f"Invalid key(s) specified in {user_config}:\n"
        for entry in invalid:
            errmsg = errmsg + f"{entry} = {invalid[entry]}\n"
        errmsg = errmsg + f"\nCheck {default_config} for allowed user-specified variables\n"
        raise Exception(errmsg)

    # Mandatory variables *must* be set in the user's config; the default value is invalid
    mandatory = ["user.MACHINE"]
    for val in mandatory:
        sect, key = val.split(".")
        user_setting = cfg_u.get(sect, {}).get(key)
        if user_setting is None:
            raise Exception(
                f"""Mandatory variable "{val}" not found in
            user config file {user_config}"""
            )

    # Load the machine config file
    machine = uppercase(cfg_u.get("user").get("MACHINE"))
    cfg_u["user"]["MACHINE"] = uppercase(machine)

    machine_file = os.path.join(ushdir, "machine", f"{lowercase(machine)}.yaml")

    if not os.path.exists(machine_file):
        raise FileNotFoundError(
            dedent(
                f"""
            The machine file {machine_file} does not exist.
            Check that you have specified the correct machine
            ({machine}) in your config file {user_config}"""
            )
        )
    logging.debug(f"Loading machine defaults file {machine_file}")
    machine_cfg = load_config_file(machine_file)

    # Load the fixed files configuration
    cfg_f = load_config_file(
        os.path.join(ushdir, os.pardir, "parm", "fixed_files_mapping.yaml")
    )

    # Load the constants file
    cfg_c = load_config_file(os.path.join(ushdir, "constants.yaml"))

    # Update default config with the constants, the machine config, and
    # then the user_config
    # Recall: update_dict updates the second dictionary with the first,
    # and so, we update the default config settings in place with all
    # the others.

    # Constants
    update_dict(cfg_c, cfg_d)

    # Machine settings
    update_dict(machine_cfg, cfg_d)

    # Fixed files
    update_dict(cfg_f, cfg_d)

    # User settings (take precedence over all others)
    update_dict(cfg_u, cfg_d)

    # Set "Home" directory, the top-level ufs-srweather-app directory
    homedir = os.path.abspath(os.path.dirname(__file__) + os.sep + os.pardir)
    cfg_d["user"]["HOMEdir"] = homedir

    # Special logic if EXPT_BASEDIR is a relative path; see config_defaults.yaml for explanation
    expt_basedir = cfg_d["workflow"]["EXPT_BASEDIR"]
    if (not expt_basedir) or (expt_basedir[0] != "/"):
        expt_basedir = os.path.join(homedir, "..", "expt_dirs", expt_basedir)
    try:
        expt_basedir = os.path.realpath(expt_basedir)
    except:
        pass
    cfg_d["workflow"]["EXPT_BASEDIR"] = os.path.abspath(expt_basedir)

    extend_yaml(cfg_d)

    # Do any conversions of data types
    for sect, settings in cfg_d.items():
        for k, v in settings.items():
            if not (v is None or v == ""):
                cfg_d[sect][k] = str_to_list(v)

    # Mandatory variables *must* be set in the user's config or the machine file; the default value is invalid
    mandatory = [
        "EXPT_SUBDIR",
        "NCORES_PER_NODE",
        "FIXgsm",
        "FIXaer",
        "FIXlut",
        "FIXorg",
        "FIXsfc",
    ]
    flat_cfg = flatten_dict(cfg_d)
    for val in mandatory:
        if not flat_cfg.get(val):
            raise Exception(
                dedent(
                    f"""
                    Mandatory variable "{val}" not found in:
                    user config file {user_config}
                                  OR
                    machine file {machine_file} 
                    """
                )
            )

    # Check that input dates are in a date format
    dates = ["DATE_FIRST_CYCL", "DATE_LAST_CYCL"]
    for val in dates:
        if not isinstance(cfg_d["workflow"][val], datetime.date):
            raise Exception(
                dedent(
                    f"""
                            Date variable {val}={cfg_d['workflow'][val]} is not in a valid date format.

                            For examples of valid formats, see the Users' Guide.
                            """
                )
            )

    return cfg_d


def set_srw_paths(ushdir, expt_config):

    """
    Generate a dictionary of directories that describe the SRW
    structure, i.e., where SRW is installed, and the paths to
    external repositories managed via the manage_externals tool.

    Other paths for SRW are set as defaults in config_defaults.yaml

    Args:
       ushdir:      (str) path to the system location of the ush/ directory
                     under the SRW clone
       expt_config: (dict) contains the configuration settings for the
                     user-defined experiment

    Returns:
       dictionary of config settings and system paths as keys/values
    """

    # HOMEdir is the location of the SRW clone, one directory above ush/
    homedir = expt_config.get("user", {}).get("HOMEdir")

    # Read Externals.cfg
    mng_extrns_cfg_fn = os.path.join(homedir, "Externals.cfg")
    try:
        mng_extrns_cfg_fn = os.readlink(mng_extrns_cfg_fn)
    except:
        pass
    cfg = load_ini_config(mng_extrns_cfg_fn)

    # Get the base directory of the FV3 forecast model code.
    external_name = expt_config.get("workflow", {}).get("FCST_MODEL")
    property_name = "local_path"

    try:
        ufs_wthr_mdl_dir = get_ini_value(cfg, external_name, property_name)
    except KeyError:
        errmsg = dedent(
            f"""
            Externals configuration file {mng_extrns_cfg_fn}
            does not contain '{external_name}'."""
        )
        raise Exception(errmsg) from None

    # Check that the model code has been downloaded
    ufs_wthr_mdl_dir = os.path.join(homedir, ufs_wthr_mdl_dir)
    if not os.path.exists(ufs_wthr_mdl_dir):
        raise FileNotFoundError(
            dedent(
                f"""
                The base directory in which the FV3 source code should be located
                (UFS_WTHR_MDL_DIR) does not exist:
                  UFS_WTHR_MDL_DIR = '{ufs_wthr_mdl_dir}'
                Please clone the external repository containing the code in this directory,
                build the executable, and then rerun the workflow."""
            )
        )

    return dict(
        USHdir=ushdir,
        UFS_WTHR_MDL_DIR=ufs_wthr_mdl_dir,
    )


def setup(USHdir, user_config_fn="config.yaml", debug: bool = False):
    """Function that validates user-provided configuration, and derives
    a secondary set of parameters needed to configure a Rocoto-based SRW
    workflow. The derived parameters use a set of required user-defined
    parameters defined by either config_defaults.yaml, a user-provided
    configuration file (config.yaml), or a YAML machine file.

    A set of global variable definitions is saved to the experiment
    directory as a bash configure file that is sourced by scripts at run
    time.

    Args:
      USHdir          (str): The full path of the ush/ directory where
                             this script is located
      user_config_fn  (str): The name of a user-provided config YAML
      debug          (bool): Enable extra output for debugging

    Returns:
      None
    """

    logger = logging.getLogger(__name__)

    # print message
    log_info(
        f"""
        ========================================================================
        Starting function setup() in \"{os.path.basename(__file__)}\"...
        ========================================================================"""
    )

    # Create a dictionary of config options from defaults, machine, and
    # user config files.
    default_config_fp = os.path.join(USHdir, "config_defaults.yaml")
    user_config_fp = os.path.join(USHdir, user_config_fn)
    expt_config = load_config_for_setup(USHdir, default_config_fp, user_config_fp)

    # Set up some paths relative to the SRW clone
    expt_config["user"].update(set_srw_paths(USHdir, expt_config))

    #
    # -----------------------------------------------------------------------
    #
    # Validate the experiment configuration starting with the workflow,
    # then in rough order of the tasks in the workflow
    #
    # -----------------------------------------------------------------------
    #

    # Workflow
    workflow_config = expt_config["workflow"]

    # Generate a unique number for this workflow run. This may be used to
    # get unique log file names for example
    workflow_id = "id_" + str(int(datetime.datetime.now().timestamp()))
    workflow_config["WORKFLOW_ID"] = workflow_id
    log_info(f"""WORKFLOW ID = {workflow_id}""")

    debug = workflow_config.get("DEBUG")
    if debug:
        log_info(
            """
            Setting VERBOSE to \"TRUE\" because DEBUG has been set to \"TRUE\"..."""
        )
        workflow_config["VERBOSE"] = True

    verbose = workflow_config["VERBOSE"]

    # The forecast length (in integer hours) cannot contain more than 3 characters.
    # Thus, its maximum value is 999.
    fcst_len_hrs_max = 999
    fcst_len_hrs = workflow_config.get("FCST_LEN_HRS")
    if fcst_len_hrs > fcst_len_hrs_max:
        raise ValueError(
            f"""
            Forecast length is greater than maximum allowed length:
              FCST_LEN_HRS = {fcst_len_hrs}
              fcst_len_hrs_max = {fcst_len_hrs_max}"""
        )


    #
    # -----------------------------------------------------------------------
    #
    # Set the full path to the experiment directory.  Then check if it already
    # exists and if so, deal with it as specified by PREEXISTING_DIR_METHOD.
    #
    # -----------------------------------------------------------------------
    #

    expt_subdir = workflow_config.get("EXPT_SUBDIR", "")
    exptdir = workflow_config.get("EXPTDIR")

    # Update some paths that include EXPTDIR and EXPT_BASEDIR
    extend_yaml(expt_config)
    preexisting_dir_method = workflow_config.get("PREEXISTING_DIR_METHOD", "")
    try:
        check_for_preexist_dir_file(exptdir, preexisting_dir_method)
    except ValueError:
        logger.exception(
            f"""
            Check that the following values are valid:
            EXPTDIR {exptdir}
            PREEXISTING_DIR_METHOD {preexisting_dir_method}
            """
        )
        raise
    except FileExistsError:
        errmsg = dedent(
            f"""
            EXPTDIR ({exptdir}) already exists, and PREEXISTING_DIR_METHOD = {preexisting_dir_method}

            To ignore this error, delete the directory, or set 
            PREEXISTING_DIR_METHOD = delete, or
            PREEXISTING_DIR_METHOD = rename
            in your config file.
            """
        )
        raise FileExistsError(errmsg) from None

    #
    # -----------------------------------------------------------------------
    #
    # Set cron table entry for relaunching the workflow if
    # USE_CRON_TO_RELAUNCH is set to TRUE.
    #
    # -----------------------------------------------------------------------
    #
    if workflow_config.get("USE_CRON_TO_RELAUNCH"):
        intvl_mnts = workflow_config.get("CRON_RELAUNCH_INTVL_MNTS")
        launch_script_fn = workflow_config.get("WFLOW_LAUNCH_SCRIPT_FN")
        launch_log_fn = workflow_config.get("WFLOW_LAUNCH_LOG_FN")
        workflow_config["CRONTAB_LINE"] = (
            f"""*/{intvl_mnts} * * * * cd {exptdir} && """
            f"""./{launch_script_fn} called_from_cron="TRUE" >> ./{launch_log_fn} 2>&1"""
        )
    #
    # -----------------------------------------------------------------------
    #
    # Check user settings against platform settings
    #
    # -----------------------------------------------------------------------
    #

    workflow_switches = expt_config["workflow_switches"]
    run_task_make_grid = workflow_switches['RUN_TASK_MAKE_GRID']
    run_task_make_orog = workflow_switches['RUN_TASK_MAKE_OROG']
    run_task_make_sfc_climo = workflow_switches['RUN_TASK_MAKE_SFC_CLIMO']

    # Necessary tasks are turned on
    pregen_basedir = expt_config["platform"].get("DOMAIN_PREGEN_BASEDIR")
    if pregen_basedir is None and not (
        run_task_make_grid and run_task_make_orog and run_task_make_sfc_climo
    ):
        raise Exception(
            f"""
            DOMAIN_PREGEN_BASEDIR must be set when any of the following
            tasks are turned off:
                RUN_TASK_MAKE_GRID = {run_task_make_grid}
                RUN_TASK_MAKE_OROG = {run_task_make_orog}
                RUN_TASK_MAKE_SFC_CLIMO = {run_task_make_sfc_climo}"""
        )

    # A batch system account is specified
    if expt_config["platform"].get("WORKFLOW_MANAGER") is not None:
        if not expt_config.get("user").get("ACCOUNT"):
            raise Exception(
                dedent(
                    f"""
                  ACCOUNT must be specified in config or machine file if using a workflow manager.
                  WORKFLOW_MANAGER = {expt_config["platform"].get("WORKFLOW_MANAGER")}\n"""
                )
            )

    #
    # -----------------------------------------------------------------------
    #
    # ICS and LBCS settings and validation
    #
    # -----------------------------------------------------------------------
    #
    def get_location(xcs, fmt, expt_cfg):
        ics_lbcs = expt_cfg.get("data", {}).get("ics_lbcs")
        if ics_lbcs is not None:
            v = ics_lbcs.get(xcs)
            if not isinstance(v, dict):
                return v
            else:
                return v.get(fmt, "")
        else:
            return ""

    # Get the paths to any platform-supported data streams
    get_extrn_ics = expt_config.get("task_get_extrn_ics", {})
    extrn_mdl_sysbasedir_ics = get_location(
        get_extrn_ics.get("EXTRN_MDL_NAME_ICS"),
        get_extrn_ics.get("FV3GFS_FILE_FMT_ICS"),
        expt_config,
    )
    get_extrn_ics["EXTRN_MDL_SYSBASEDIR_ICS"] = extrn_mdl_sysbasedir_ics

    get_extrn_lbcs = expt_config.get("task_get_extrn_lbcs", {})
    extrn_mdl_sysbasedir_lbcs = get_location(
        get_extrn_lbcs.get("EXTRN_MDL_NAME_LBCS"),
        get_extrn_lbcs.get("FV3GFS_FILE_FMT_LBCS"),
        expt_config,
    )
    get_extrn_lbcs["EXTRN_MDL_SYSBASEDIR_LBCS"] = extrn_mdl_sysbasedir_lbcs

    # remove the data key -- it's not needed beyond this point
    if "data" in expt_config:
        expt_config.pop("data")

    # Check for the user-specified directories for external model files if
    # USE_USER_STAGED_EXTRN_FILES is set to TRUE
    task_keys = zip(
        [get_extrn_ics, get_extrn_lbcs],
        ["EXTRN_MDL_SOURCE_BASEDIR_ICS", "EXTRN_MDL_SOURCE_BASEDIR_LBCS"],
    )

    for task, data_key in task_keys:
        use_staged_extrn_files = task.get("USE_USER_STAGED_EXTRN_FILES")
        if use_staged_extrn_files:
            basedir = task[data_key]
            # Check for the base directory up to the first templated field.
            idx = basedir.find("$")
            if idx == -1:
                idx = len(basedir)

            if not os.path.exists(basedir[:idx]):
                raise FileNotFoundError(
                    f'''
                    The user-staged-data directory does not exist.
                    Please point to the correct path where your external
                    model files are stored.
                      {data_key} = \"{basedir}\"'''
                )

    #
    # -----------------------------------------------------------------------
    #
    # Forecast settings
    #
    # -----------------------------------------------------------------------
    #

    fcst_config = expt_config["task_run_fcst"]
    grid_config = expt_config["task_make_grid"]

    # Warn if user has specified a large timestep inappropriately
    hires_ccpp_suites = ["FV3_RRFS_v1beta", "FV3_WoFS_v0", "FV3_HRRR"]
    if workflow_config["CCPP_PHYS_SUITE"] in hires_ccpp_suites:
        dt = fcst_config.get("DT_ATMOS")
        if dt:
            if dt > 40:
                logger.warning(dedent(
                    f"""
                    WARNING: CCPP suite {workflow_config["CCPP_PHYS_SUITE"]} requires short
                    time step regardless of grid resolution. The user-specified value
                    DT_ATMOS = {fcst_config.get("DT_ATMOS")}
                    may result in CFL violations or other errors!
                    """
                ))

    # Gather the pre-defined grid parameters, if needed
    if workflow_config.get("PREDEF_GRID_NAME"):
        grid_params = set_predef_grid_params(
            USHdir,
            workflow_config["PREDEF_GRID_NAME"],
            fcst_config["QUILTING"],
        )

        # Users like to change these variables, so don't overwrite them
        special_vars = ["DT_ATMOS", "LAYOUT_X", "LAYOUT_Y", "BLOCKSIZE"]
        for param, value in grid_params.items():
            if param in special_vars:
                param_val = fcst_config.get(param)
                if param_val and isinstance(param_val, str) and "{{" not in param_val:
                    continue
                elif isinstance(param_val, (int, float)):
                    continue
                # DT_ATMOS needs special treatment based on CCPP suite
                elif param == "DT_ATMOS":
                    if workflow_config["CCPP_PHYS_SUITE"] in hires_ccpp_suites and grid_params[param] > 40:
                        logger.warning(dedent(
                            f"""
                            WARNING: CCPP suite {workflow_config["CCPP_PHYS_SUITE"]} requires short
                            time step regardless of grid resolution; setting DT_ATMOS to 40.\n
                            This value can be overwritten in the user config file.
                            """
                        ))
                        fcst_config[param] = 40
                    else:
                        fcst_config[param] = value
                else:
                    fcst_config[param] = value
            elif param.startswith("WRTCMP"):
                fcst_config[param] = value
            elif param == "GRID_GEN_METHOD":
                workflow_config[param] = value
            else:
                grid_config[param] = value

    run_envir = expt_config["user"].get("RUN_ENVIR", "")

    # set varying forecast lengths only when fcst_len_hrs=-1
    fcst_len_hrs = workflow_config.get("FCST_LEN_HRS")
    if fcst_len_hrs == -1:
        # Create a full list of cycle dates
        fcst_len_cycl = workflow_config.get("FCST_LEN_CYCL")
        num_fcst_len_cycl = len(fcst_len_cycl)
        date_first_cycl = workflow_config.get("DATE_FIRST_CYCL")
        date_last_cycl = workflow_config.get("DATE_LAST_CYCL")
        incr_cycl_freq = workflow_config.get("INCR_CYCL_FREQ")
        all_cdates = set_cycle_dates(date_first_cycl,date_last_cycl,incr_cycl_freq)
        num_all_cdates = len(all_cdates)
        # Create a full list of forecast hours
        num_recur = num_all_cdates // num_fcst_len_cycl
        rem_recur = num_all_cdates % num_fcst_len_cycl
        if rem_recur == 0:
            fcst_len_cycl = fcst_len_cycl * num_recur
            num_fcst_len_cycl = len(fcst_len_cycl)
            workflow_config["FCST_LEN_CYCL"] = fcst_len_cycl
            workflow_config.update({"ALL_CDATES": all_cdates})
        else:
            raise Exception(
                f"""
                The number of the cycle dates is not evenly divisible by the
                number of the forecast lengths:
                  num_all_cdates = {num_all_cdates}
                  num_fcst_len_cycl = {num_fcst_len_cycl}
                  rem = num_all_cdates%%num_fcst_len_cycl = {rem_recur}"""
            )
        if num_fcst_len_cycl != num_all_cdates:
            raise Exception(
                f"""
                The number of the cycle dates does not match with the number of
                the forecast lengths:
                  num_all_cdates = {num_all_cdates}
                  num_fcst_len_cycl = {num_fcst_len_cycl}"""
            )

    #
    # -----------------------------------------------------------------------
    #
    # Set parameters according to the type of horizontal grid generation
    # method specified.
    #
    # -----------------------------------------------------------------------
    #
    grid_gen_method = workflow_config["GRID_GEN_METHOD"]
    if grid_gen_method == "GFDLgrid":
        grid_params = set_gridparams_GFDLgrid(
            lon_of_t6_ctr=grid_config["GFDLgrid_LON_T6_CTR"],
            lat_of_t6_ctr=grid_config["GFDLgrid_LAT_T6_CTR"],
            res_of_t6g=grid_config["GFDLgrid_NUM_CELLS"],
            stretch_factor=grid_config["GFDLgrid_STRETCH_FAC"],
            refine_ratio_t6g_to_t7g=grid_config["GFDLgrid_REFINE_RATIO"],
            istart_of_t7_on_t6g=grid_config["GFDLgrid_ISTART_OF_RGNL_DOM_ON_T6G"],
            iend_of_t7_on_t6g=grid_config["GFDLgrid_IEND_OF_RGNL_DOM_ON_T6G"],
            jstart_of_t7_on_t6g=grid_config["GFDLgrid_JSTART_OF_RGNL_DOM_ON_T6G"],
            jend_of_t7_on_t6g=grid_config["GFDLgrid_JEND_OF_RGNL_DOM_ON_T6G"],
            verbose=verbose,
            nh4=expt_config["constants"]["NH4"],
            run_envir=run_envir,
        )
    elif grid_gen_method == "ESGgrid":
        grid_params = set_gridparams_ESGgrid(
            lon_ctr=grid_config["ESGgrid_LON_CTR"],
            lat_ctr=grid_config["ESGgrid_LAT_CTR"],
            nx=grid_config["ESGgrid_NX"],
            ny=grid_config["ESGgrid_NY"],
            pazi=grid_config["ESGgrid_PAZI"],
            halo_width=grid_config["ESGgrid_WIDE_HALO_WIDTH"],
            delx=grid_config["ESGgrid_DELX"],
            dely=grid_config["ESGgrid_DELY"],
            constants=expt_config["constants"],
        )
    else:

        errmsg = dedent(
            f"""
            Valid values of GRID_GEN_METHOD are GFDLgrid and ESGgrid.
            The value provided is:
              GRID_GEN_METHOD = {grid_gen_method}
            """
        )
        raise KeyError(errmsg) from None

    # Add a grid parameter section to the experiment config
    expt_config["grid_params"] = grid_params

    # Check to make sure that mandatory forecast variables are set.
    vlist = [
        "DT_ATMOS",
        "LAYOUT_X",
        "LAYOUT_Y",
        "BLOCKSIZE",
    ]
    for val in vlist:
        if not fcst_config.get(val):
            raise Exception(f"\nMandatory variable '{val}' has not been set\n")

    #
    # -----------------------------------------------------------------------
    #
    # Set magnitude of stochastic ad-hoc schemes to -999.0 if they are not
    # being used. This is required at the moment, since "do_shum/sppt/skeb"
    # does not override the use of the scheme unless the magnitude is also
    # specifically set to -999.0.  If all "do_shum/sppt/skeb" are set to
    # "false," then none will run, regardless of the magnitude values.
    #
    # -----------------------------------------------------------------------
    #
    global_sect = expt_config["global"]
    if not global_sect.get("DO_SHUM"):
        global_sect["SHUM_MAG"] = -999.0
    if not global_sect.get("DO_SKEB"):
        global_sect["SKEB_MAG"] = -999.0
    if not global_sect.get("DO_SPPT"):
        global_sect["SPPT_MAG"] = -999.0
    #
    # -----------------------------------------------------------------------
    #
    # If running with SPP in MYNN PBL, MYNN SFC, GSL GWD, Thompson MP, or
    # RRTMG, count the number of entries in SPP_VAR_LIST to correctly set
    # N_VAR_SPP, otherwise set it to zero.
    #
    # -----------------------------------------------------------------------
    #
    if global_sect.get("DO_SPP"):
        global_sect["N_VAR_SPP"] = len(global_sect["SPP_VAR_LIST"])
    else:
        global_sect["N_VAR_SPP"] = 0
    #
    # -----------------------------------------------------------------------
    #
    # If running with SPP, confirm that each SPP-related namelist value
    # contains the same number of entries as N_VAR_SPP (set above to be equal
    # to the number of entries in SPP_VAR_LIST).
    #
    # -----------------------------------------------------------------------
    #
    spp_vars = [
        "SPP_MAG_LIST",
        "SPP_LSCALE",
        "SPP_TSCALE",
        "SPP_SIGTOP1",
        "SPP_SIGTOP2",
        "SPP_STDDEV_CUTOFF",
        "ISEED_SPP",
    ]

    if global_sect.get("DO_SPP"):
        for spp_var in spp_vars:
            if len(global_sect[spp_var]) != global_sect["N_VAR_SPP"]:
                raise Exception(
                    f"""
                    All MYNN PBL, MYNN SFC, GSL GWD, Thompson MP, or RRTMG SPP-related namelist
                    variables must be of equal length to SPP_VAR_LIST:
                      SPP_VAR_LIST (length {global_sect['N_VAR_SPP']})
                      {spp_var} (length {len(global_sect[spp_var])})
                    """
                )
    #
    # -----------------------------------------------------------------------
    #
    # If running with Noah or RUC-LSM SPP, count the number of entries in
    # LSM_SPP_VAR_LIST to correctly set N_VAR_LNDP, otherwise set it to zero.
    # Also set LNDP_TYPE to 2 for LSM SPP, otherwise set it to zero.  Finally,
    # initialize an "FHCYC_LSM_SPP" variable to 0 and set it to 999 if LSM SPP
    # is turned on.  This requirement is necessary since LSM SPP cannot run with
    # FHCYC=0 at the moment, but FHCYC cannot be set to anything less than the
    # length of the forecast either.  A bug fix will be submitted to
    # ufs-weather-model soon, at which point, this requirement can be removed
    # from regional_workflow.
    #
    # -----------------------------------------------------------------------
    #
    if global_sect.get("DO_LSM_SPP"):
        global_sect["N_VAR_LNDP"] = len(global_sect["LSM_SPP_VAR_LIST"])
        global_sect["LNDP_TYPE"] = 2
        global_sect["LNDP_MODEL_TYPE"] = 2
        global_sect["FHCYC_LSM_SPP_OR_NOT"] = 999
    else:
        global_sect["N_VAR_LNDP"] = 0
        global_sect["LNDP_TYPE"] = 0
        global_sect["LNDP_MODEL_TYPE"] = 0
        global_sect["FHCYC_LSM_SPP_OR_NOT"] = 0
    #
    # -----------------------------------------------------------------------
    #
    # If running with LSM SPP, confirm that each LSM SPP-related namelist
    # value contains the same number of entries as N_VAR_LNDP (set above to
    # be equal to the number of entries in LSM_SPP_VAR_LIST).
    #
    # -----------------------------------------------------------------------
    #
    lsm_spp_vars = [
        "LSM_SPP_MAG_LIST",
        "LSM_SPP_LSCALE",
        "LSM_SPP_TSCALE",
    ]
    if global_sect.get("DO_LSM_SPP"):
        for lsm_spp_var in lsm_spp_vars:
            if len(global_sect[lsm_spp_var]) != global_sect["N_VAR_LNDP"]:
                raise Exception(
                    f"""
                    All MYNN PBL, MYNN SFC, GSL GWD, Thompson MP, or RRTMG SPP-related namelist
                    variables must be of equal length to SPP_VAR_LIST:
                    All Noah or RUC-LSM SPP-related namelist variables (except ISEED_LSM_SPP)
                    must be equal of equal length to LSM_SPP_VAR_LIST:
                      LSM_SPP_VAR_LIST (length {global_sect['N_VAR_LNDP']})
                      {lsm_spp_var} (length {len(global_sect[lsm_spp_var])}
                      """
                )

    # Check whether the forecast length (FCST_LEN_HRS) is evenly divisible
    # by the BC update interval (LBC_SPEC_INTVL_HRS). If so, generate an
    # array of forecast hours at which the boundary values will be updated.

    lbc_spec_intvl_hrs = get_extrn_lbcs.get("LBC_SPEC_INTVL_HRS")
    rem = fcst_len_hrs % lbc_spec_intvl_hrs
    if rem != 0 and fcst_len_hrs > 0:
        raise Exception(
            f"""
            The forecast length (FCST_LEN_HRS) is not evenly divisible by the lateral
            boundary conditions update interval (LBC_SPEC_INTVL_HRS):
              FCST_LEN_HRS = {fcst_len_hrs}
              LBC_SPEC_INTVL_HRS = {lbc_spec_intvl_hrs}
              rem = FCST_LEN_HRS%%LBC_SPEC_INTVL_HRS = {rem}"""
        )

    #
    # -----------------------------------------------------------------------
    #
    # Post-processing validation and settings
    #
    # -----------------------------------------------------------------------
    #

    # If using a custom post configuration file, make sure that it exists.
    post_config = expt_config["task_run_post"]
    if post_config.get("USE_CUSTOM_POST_CONFIG_FILE"):
        custom_post_config_fp = post_config.get("CUSTOM_POST_CONFIG_FP")
        try:
            # os.path.exists returns exception if passed None, so use
            # "try/except" to catch it and the non-existence of a
            # provided path
            if not os.path.exists(custom_post_config_fp):
                raise FileNotFoundError(
                    dedent(
                        f"""
                    USE_CUSTOM_POST_CONFIG_FILE has been set, but the custom post configuration file
                    CUSTOM_POST_CONFIG_FP = {custom_post_config_fp}
                    could not be found."""
                    )
                ) from None
        except TypeError:
            raise TypeError(
                dedent(
                    f"""
                USE_CUSTOM_POST_CONFIG_FILE has been set, but the custom
                post configuration file path (CUSTOM_POST_CONFIG_FP) is
                None.
                """
                )
            ) from None
        except FileNotFoundError:
            raise

    # If using external CRTM fix files to allow post-processing of synthetic
    # satellite products from the UPP, make sure the CRTM fix file directory exists.
    if global_sect.get("USE_CRTM"):
        crtm_dir = global_sect.get("CRTM_DIR")
        try:
            # os.path.exists returns exception if passed None, so use
            # "try/except" to catch it and the non-existence of a
            # provided path
            if not os.path.exists(crtm_dir):
                raise FileNotFoundError(
                    dedent(
                        f"""
                    USE_CRTM has been set, but the external CRTM fix file directory:
                    CRTM_DIR = {crtm_dir}
                    could not be found."""
                    )
                ) from None
        except TypeError:
            raise TypeError(
                dedent(
                    f"""
                USE_CRTM has been set, but the external CRTM fix file
                directory (CRTM_DIR) is None.
                """
                )
            ) from None
        except FileNotFoundError:
            raise

    # If performing sub-hourly model output and post-processing, check that
    # the output interval DT_SUBHOURLY_POST_MNTS (in minutes) is specified
    # correctly.
    if post_config.get("SUB_HOURLY_POST"):

        # Subhourly post should be set with minutes between 1 and 59 for
        # real subhourly post to be performed.
        dt_subhourly_post_mnts = post_config.get("DT_SUBHOURLY_POST_MNTS")
        if dt_subhourly_post_mnts == 0:
            logger.warning(
                f"""
                When performing sub-hourly post (i.e. SUB_HOURLY_POST set to \"TRUE\"),
                DT_SUBHOURLY_POST_MNTS must be set to a value greater than 0; otherwise,
                sub-hourly output is not really being performed:
                  DT_SUBHOURLY_POST_MNTS = \"{DT_SUBHOURLY_POST_MNTS}\"
                Resetting SUB_HOURLY_POST to \"FALSE\".  If you do not want this, you
                must set DT_SUBHOURLY_POST_MNTS to something other than zero."""
            )
            post_config["SUB_HOURLY_POST"] = False

        if dt_subhourly_post_mnts < 1 or dt_subhourly_post_mnts > 59:
            raise ValueError(
                f'''
                When SUB_HOURLY_POST is set to \"TRUE\",
                DT_SUBHOURLY_POST_MNTS must be set to an integer between 1 and 59,
                inclusive but:
                  DT_SUBHOURLY_POST_MNTS = \"{dt_subhourly_post_mnts}\"'''
            )

        # Check that DT_SUBHOURLY_POST_MNTS (after converting to seconds) is
        # evenly divisible by the forecast model's main time step DT_ATMOS.
        dt_atmos = fcst_config["DT_ATMOS"]
        rem = dt_subhourly_post_mnts * 60 % dt_atmos
        if rem != 0:
            raise ValueError(
                f"""
                When SUB_HOURLY_POST is set to \"TRUE\") the post
                processing interval in seconds must be evenly divisible
                by the time step DT_ATMOS used in the forecast model,
                i.e. the remainder must be zero.  In this case, it is
                not:

                  DT_SUBHOURLY_POST_MNTS = \"{dt_subhourly_post_mnts}\"
                  DT_ATMOS = \"{dt_atmos}\"
                  remainder = (DT_SUBHOURLY_POST_MNTS*60) %% DT_ATMOS = {rem}

                Please reset DT_SUBHOURLY_POST_MNTS and/or DT_ATMOS so
                that this remainder is zero."""
            )

    # Make sure the post output domain is set
    predef_grid_name = workflow_config.get("PREDEF_GRID_NAME")
    post_output_domain_name = post_config.get("POST_OUTPUT_DOMAIN_NAME")

    if not post_output_domain_name:
        if not predef_grid_name:
            raise Exception(
                f"""
                The domain name used in naming the run_post output files
                (POST_OUTPUT_DOMAIN_NAME) has not been set:
                POST_OUTPUT_DOMAIN_NAME = \"{post_output_domain_name}\"
                If this experiment is not using a predefined grid (i.e. if
                PREDEF_GRID_NAME is set to a null string), POST_OUTPUT_DOMAIN_NAME
                must be set in the configuration file (\"{user_config}\"). """
            )
        post_output_domain_name = predef_grid_name

    if not isinstance(post_output_domain_name, int):
        post_output_domain_name = lowercase(post_output_domain_name)

    # Write updated value of POST_OUTPUT_DOMAIN_NAME back to dictionary
    post_config["POST_OUTPUT_DOMAIN_NAME"] = post_output_domain_name 

    #
    # -----------------------------------------------------------------------
    #
    # Set the output directory locations
    #
    # -----------------------------------------------------------------------
    #

    # These NCO variables need to be set based on the user's specified
    # run environment. The default is set in config_defaults for nco. If
    # running in community mode, we set these paths to the experiment
    # directory.
    nco_vars = [
        "opsroot",
        "comroot",
        "packageroot",
        "dataroot",
        "dcomroot",
        "comin_basedir",
        "comout_basedir",
        "extroot",
    ]

    nco_config = expt_config["nco"]
    if run_envir != "nco":
        # Put the variables in config dict.
        for nco_var in nco_vars:
            nco_config[nco_var.upper()] = exptdir

        nco_config["LOGBASEDIR"] = os.path.join(exptdir, "log")

    # Use env variables for NCO variables and create NCO directories
    if run_envir == "nco":

        for nco_var in nco_vars:
            envar = os.environ.get(nco_var)
            if envar is not None:
                nco_config[nco_var.upper()] = envar

        mkdir_vrfy(f' -p "{nco_config.get("OPSROOT")}"')
        mkdir_vrfy(f' -p "{nco_config.get("COMROOT")}"')
        mkdir_vrfy(f' -p "{nco_config.get("PACKAGEROOT")}"')
        mkdir_vrfy(f' -p "{nco_config.get("DATAROOT")}"')
        mkdir_vrfy(f' -p "{nco_config.get("DCOMROOT")}"')
        mkdir_vrfy(f' -p "{nco_config.get("LOGBASEDIR")}"')
        mkdir_vrfy(f' -p "{nco_config.get("EXTROOT")}"')
    if nco_config["DBNROOT"]:
        mkdir_vrfy(f' -p "{nco_config["DBNROOT"]}"')

    # create experiment dir
    mkdir_vrfy(f' -p "{exptdir}"')

    # -----------------------------------------------------------------------
    #
    # The FV3 forecast model needs the following input files in the run
    # directory to start a forecast:
    #
    #   (1) The data table file
    #   (2) The diagnostics table file
    #   (3) The field table file
    #   (4) The FV3 namelist file
    #   (5) The model configuration file
    #   (6) The NEMS configuration file
    #   (7) The CCPP physics suite definition file
    #
    # The workflow contains templates for the first six of these files.
    # Template files are versions of these files that contain placeholder
    # (i.e. dummy) values for various parameters.  The experiment/workflow
    # generation scripts copy these templates to appropriate locations in
    # the experiment directory (either the top of the experiment directory
    # or one of the cycle subdirectories) and replace the placeholders in
    # these copies by actual values specified in the experiment/workflow
    # configuration file (or derived from such values).  The scripts then
    # use the resulting "actual" files as inputs to the forecast model.
    #
    # Note that the CCPP physics suite definition file does not have a
    # corresponding template file because it does not contain any values
    # that need to be replaced according to the experiment/workflow
    # configuration.  If using CCPP, this file simply needs to be copied
    # over from its location in the forecast model's directory structure
    # to the experiment directory.
    #
    # Below, we first set the names of the templates for the first six files
    # listed above.  We then set the full paths to these template files.
    # Note that some of these file names depend on the physics suite while
    # others do not.
    #
    # -----------------------------------------------------------------------
    #
    # Check for the CCPP_PHYSICS suite xml file
    ccpp_phys_suite_in_ccpp_fp = workflow_config["CCPP_PHYS_SUITE_IN_CCPP_FP"]
    if not os.path.exists(ccpp_phys_suite_in_ccpp_fp):
        raise FileNotFoundError(
            f"""
            The CCPP suite definition file (CCPP_PHYS_SUITE_IN_CCPP_FP) does not exist
            in the local clone of the ufs-weather-model:
              CCPP_PHYS_SUITE_IN_CCPP_FP = '{ccpp_phys_suite_in_ccpp_fp}'"""
        )

    # Check for the field dict file
    field_dict_in_uwm_fp = workflow_config["FIELD_DICT_IN_UWM_FP"]
    if not os.path.exists(field_dict_in_uwm_fp):
        raise FileNotFoundError(
            f"""
            The field dictionary file (FIELD_DICT_IN_UWM_FP) does not exist
            in the local clone of the ufs-weather-model:
              FIELD_DICT_IN_UWM_FP = '{field_dict_in_uwm_fp}'"""
        )

    fixed_files = expt_config["fixed_files"]
    # Set the appropriate ozone production/loss file paths and symlinks
    ozone_param, fixgsm_ozone_fn, ozone_link_mappings = set_ozone_param(
        ccpp_phys_suite_in_ccpp_fp,
        fixed_files["CYCLEDIR_LINKS_TO_FIXam_FILES_MAPPING"],
    )

    # Reset the dummy value saved in the last list item to the ozone
    # file name
    fixed_files["FIXgsm_FILES_TO_COPY_TO_FIXam"][-1] = fixgsm_ozone_fn

    # Reset the experiment config list with the update list
    fixed_files["CYCLEDIR_LINKS_TO_FIXam_FILES_MAPPING"] = ozone_link_mappings

    log_info(
        f"""
        The ozone parameter used for this experiment is {ozone_param}.
        """
    )

    log_info(
        f"""
        The list that sets the mapping between symlinks in the cycle
        directory, and the files in the FIXam directory has been updated
        to include the ozone production/loss file.
        """,
        verbose=verbose,
    )

    log_info(
        f"""
        CYCLEDIR_LINKS_TO_FIXam_FILES_MAPPING = {list_to_str(ozone_link_mappings)}
        """,
        verbose=verbose,
        dedent_=False,
    )

    #
    # -----------------------------------------------------------------------
    #
    # Check that the set of tasks to run in the workflow is internally
    # consistent.
    #
    # -----------------------------------------------------------------------
    #

    # Ensemble verification can only be run in ensemble mode
    do_ensemble = global_sect["DO_ENSEMBLE"]
    run_task_vx_ensgrid = workflow_switches["RUN_TASK_VX_ENSGRID"]
    run_task_vx_enspoint = workflow_switches["RUN_TASK_VX_ENSPOINT"]
    if (not do_ensemble) and (run_task_vx_ensgrid or run_task_vx_enspoint):
        raise Exception(
            f'''
            Ensemble verification can not be run unless running in ensemble mode:
               DO_ENSEMBLE = \"{do_ensemble}\"
               RUN_TASK_VX_ENSGRID = \"{run_task_vx_ensgrid}\"
               RUN_TASK_VX_ENSPOINT = \"{run_task_vx_enspoint}\"'''
        )

    #
    # -----------------------------------------------------------------------
    # NOTE: currently this is executed no matter what, should it be dependent on the logic described below??
    # If not running the TN_MAKE_GRID, TN_MAKE_OROG, and/or TN_MAKE_SFC_CLIMO
    # tasks, create symlinks under the FIXlam directory to pregenerated grid,
    # orography, and surface climatology files.
    #
    # -----------------------------------------------------------------------
    #
    fixlam = workflow_config["FIXlam"]
    mkdir_vrfy(f' -p "{fixlam}"')

    #
    # Use the pregenerated domain files if the RUN_TASK_MAKE* tasks are
    # turned off. Link the files, and check that they all contain the
    # same resolution input.
    #
    run_task_make_ics = workflow_switches['RUN_TASK_MAKE_LBCS']
    run_task_make_lbcs = workflow_switches['RUN_TASK_MAKE_ICS']
    run_task_run_fcst = workflow_switches['RUN_TASK_RUN_FCST']
    run_task_makeics_or_makelbcs_or_runfcst = run_task_make_ics or \
                                              run_task_make_lbcs or \
                                              run_task_run_fcst
    # Flags for creating symlinks to pre-generated grid, orography, and sfc_climo files.
    # These consider dependencies of other tasks on each pre-processing task.
    create_symlinks_to_pregen_files = {
      "GRID": (not workflow_switches['RUN_TASK_MAKE_GRID']) and \
              (run_task_make_orog or run_task_make_sfc_climo or run_task_makeics_or_makelbcs_or_runfcst),
      "OROG": (not workflow_switches['RUN_TASK_MAKE_OROG']) and \
              (run_task_make_sfc_climo or run_task_makeics_or_makelbcs_or_runfcst),
      "SFC_CLIMO": (not workflow_switches['RUN_TASK_MAKE_SFC_CLIMO']) and \
                   (run_task_make_ics or run_task_make_lbcs),
    }

    prep_tasks = ["GRID", "OROG", "SFC_CLIMO"]
    res_in_fixlam_filenames = None
    for prep_task in prep_tasks:
        res_in_fns = ""
        # If the user doesn't want to run the given task, link the fix
        # file from the staged files.
        if create_symlinks_to_pregen_files[prep_task]:
            sect_key = f"task_make_{prep_task.lower()}"
            dir_key = f"{prep_task}_DIR"
            task_dir = expt_config[sect_key].get(dir_key)

            if not task_dir:
                task_dir = os.path.join(pregen_basedir, predef_grid_name)
                expt_config[sect_key][dir_key] = task_dir
                msg = dedent(
                    f"""
                   {dir_key} will point to a location containing pre-generated files.
                   Setting {dir_key} = {task_dir}
                   """
                )
                logger.warning(msg)

            if not os.path.exists(task_dir):
                msg = dedent(
                    f"""
                    File directory does not exist!
                    {dir_key} needs {task_dir}
                    """
                )
                raise FileNotFoundError(msg)

            # Link the fix files and check that their resolution is
            # consistent
            res_in_fns = link_fix(
                verbose=verbose,
                file_group=prep_task.lower(),
                source_dir=task_dir,
                target_dir=workflow_config["FIXlam"],
                ccpp_phys_suite=workflow_config["CCPP_PHYS_SUITE"],
                constants=expt_config["constants"],
                dot_or_uscore=workflow_config["DOT_OR_USCORE"],
                nhw=grid_params["NHW"],
                run_task=False,
                sfc_climo_fields=fixed_files["SFC_CLIMO_FIELDS"],
            )
            if not res_in_fixlam_filenames:
                res_in_fixlam_filenames = res_in_fns
            else:
                if res_in_fixlam_filenames != res_in_fns:
                    raise Exception(
                        dedent(
                            f"""
                        The resolution of the pregenerated files for
                        {prep_task} do not match those that were alread
                        set:

                        Resolution in {prep_task}: {res_in_fns}
                        Resolution expected: {res_in_fixlam_filenames}
                        """
                        )
                    )

            if not os.path.exists(task_dir):
                raise FileNotFoundError(
                    f'''
                    The directory ({dir_key}) that should contain the pregenerated
                    {prep_task.lower()} files does not exist:
                      {dir_key} = \"{task_dir}\"'''
                )

    workflow_config["RES_IN_FIXLAM_FILENAMES"] = res_in_fixlam_filenames
    workflow_config["CRES"] = f"C{res_in_fixlam_filenames}"

    #
    # -----------------------------------------------------------------------
    #
    # Turn off post task if it's not consistent with the forecast's
    # user-setting of WRITE_DOPOST
    #
    # -----------------------------------------------------------------------
    #
    if fcst_config["WRITE_DOPOST"]:
        # Turn off run_post
        if workflow_switches["RUN_TASK_RUN_POST"]:
            logger.warning(
                dedent(
                    f"""
                           Inline post is turned on, deactivating post-processing tasks:
                           RUN_TASK_RUN_POST = False
                           """
                )
            )
            workflow_switches["RUN_TASK_RUN_POST"] = False

        # Check if SUB_HOURLY_POST is on
        if expt_config["task_run_post"]["SUB_HOURLY_POST"]:
            raise Exception(
                f"""
                SUB_HOURLY_POST is NOT available with Inline Post yet."""
            )
    #
    # -----------------------------------------------------------------------
    #
    # Call the function that checks whether the RUC land surface model (LSM)
    # is being called by the physics suite and sets the workflow variable
    # SDF_USES_RUC_LSM to True or False accordingly.
    #
    # -----------------------------------------------------------------------
    #
    workflow_config["SDF_USES_RUC_LSM"] = check_ruc_lsm(
        ccpp_phys_suite_fp=ccpp_phys_suite_in_ccpp_fp
    )
    #
    # -----------------------------------------------------------------------
    #
    # Check if the Thompson microphysics parameterization is being
    # called by the physics suite and modify certain workflow arrays to
    # ensure that fixed files needed by this parameterization are copied
    # to the FIXam directory and appropriate symlinks to them are
    # created in the run directories. Set the boolean flag
    # SDF_USES_THOMPSON_MP to indicates whether Thompson MP is called by
    # the physics suite.
    #
    # -----------------------------------------------------------------------
    #

    link_thompson_climo = (
        get_extrn_ics["EXTRN_MDL_NAME_ICS"] not in ["HRRR", "RAP"]
    ) or (get_extrn_lbcs["EXTRN_MDL_NAME_LBCS"] not in ["HRRR", "RAP"])
    use_thompson, mapping, fix_files = set_thompson_mp_fix_files(
        ccpp_phys_suite_fp=ccpp_phys_suite_in_ccpp_fp,
        thompson_mp_climo_fn=workflow_config["THOMPSON_MP_CLIMO_FN"],
        link_thompson_climo=link_thompson_climo,
    )

    workflow_config["SDF_USES_THOMPSON_MP"] = use_thompson

    if use_thompson:
        fixed_files["CYCLEDIR_LINKS_TO_FIXam_FILES_MAPPING"].extend(mapping)
        fixed_files["FIXgsm_FILES_TO_COPY_TO_FIXam"].extend(fix_files)

        log_info(
            f"""
            Since the Thompson microphysics parameterization is being used by this
            physics suite (CCPP_PHYS_SUITE), the names of the fixed files needed by
            this scheme have been appended to the array FIXgsm_FILES_TO_COPY_TO_FIXam,
            and the mappings between these files and the symlinks that need to be
            created in the cycle directories have been appended to the array
            CYCLEDIR_LINKS_TO_FIXam_FILES_MAPPING.  After these modifications, the
            values of these parameters are as follows:

            CCPP_PHYS_SUITE = \"{workflow_config["CCPP_PHYS_SUITE"]}\"
            """
        )
        log_info(
            f"""
                FIXgsm_FILES_TO_COPY_TO_FIXam =
                {list_to_str(fixed_files['FIXgsm_FILES_TO_COPY_TO_FIXam'])}
            """
        )
        log_info(
            f"""
                CYCLEDIR_LINKS_TO_FIXam_FILES_MAPPING =
                {list_to_str(fixed_files['CYCLEDIR_LINKS_TO_FIXam_FILES_MAPPING'])}
            """
        )
    #
    # -----------------------------------------------------------------------
    #
    # Generate var_defns.sh file in the EXPTDIR. This file contains all
    # the user-specified settings from expt_config.
    #
    # -----------------------------------------------------------------------
    #

    extend_yaml(expt_config)
    for sect, sect_keys in expt_config.items():
        for k, v in sect_keys.items():
            expt_config[sect][k] = str_to_list(v)
    extend_yaml(expt_config)

    # print content of var_defns if DEBUG=True
    all_lines = cfg_to_yaml_str(expt_config)
    log_info(all_lines, verbose=debug)

    global_var_defns_fp = workflow_config["GLOBAL_VAR_DEFNS_FP"]
    # print info message
    log_info(
        f"""
        Generating the global experiment variable definitions file here:
          GLOBAL_VAR_DEFNS_FP = '{global_var_defns_fp}'
        For more detailed information, set DEBUG to 'TRUE' in the experiment
        configuration file ('{user_config_fn}')."""
    )

    with open(global_var_defns_fp, "a") as f:
        f.write(cfg_to_shell_str(expt_config))

    #
    # -----------------------------------------------------------------------
    #
    # Check validity of parameters in one place, here in the end.
    #
    # -----------------------------------------------------------------------
    #

    # loop through the flattened expt_config and check validity of params
    cfg_v = load_config_file(os.path.join(USHdir, "valid_param_vals.yaml"))
    for k, v in flatten_dict(expt_config).items():
        if v is None or v == "":
            continue
        vkey = "valid_vals_" + k
        if (vkey in cfg_v) and not (v in cfg_v[vkey]):
            raise Exception(
                f"""
                The variable {k}={v} in the user's configuration
                does not have a valid value. Possible values are:
                    {k} = {cfg_v[vkey]}"""
            )

    return expt_config


#
# -----------------------------------------------------------------------
#
# Call the function defined above.
#
# -----------------------------------------------------------------------
#
if __name__ == "__main__":
    USHdir = os.path.dirname(os.path.abspath(__file__))
    setup(USHdir)
