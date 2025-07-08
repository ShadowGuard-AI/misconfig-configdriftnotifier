# misconfig-ConfigDriftNotifier
Monitors configuration files for changes and sends alerts (e.g., email, Slack) upon detection of drift. Utilizes `watchdog` library for file system monitoring. - Focused on Check for misconfigurations in configuration files or infrastructure definitions

## Install
`git clone https://github.com/ShadowGuardAI/misconfig-configdriftnotifier`

## Usage
`./misconfig-configdriftnotifier [params]`

## Parameters
- `-h`: Show help message and exit
- `-c`: Path to the configuration file. Defaults to config.yaml

## License
Copyright (c) ShadowGuardAI
