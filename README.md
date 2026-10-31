![Banner](banner.png)

# misconfig-ConfigDriftNotifier
Monitors configuration files for changes and sends email alerts upon detection of drift. Utilizes `watchdog` library for file system monitoring. - Focused on Check for misconfigurations in configuration files or infrastructure definitions

Slack alerting is not implemented. The Slack sender is a stub that logs a not implemented warning and prints the message locally; it makes no connection. Email is the only alert route that delivers.

Monitored paths may be relative or absolute, and may live outside the working directory; each path is resolved to its absolute form at startup and the file named is the file watched. A config whose monitored_files list is empty is refused at startup, because the daemon would watch nothing.

For email, the SMTP password is read from an environment variable, not from the config file. Set SMTP_PASSWORD, or name a different variable in the email settings with smtp_password_env. Transport encryption is used whenever the SMTP server offers STARTTLS, whether or not a login follows.

## Install
`git clone https://github.com/ShadowGuardAI/misconfig-configdriftnotifier`

## Usage
`./misconfig-configdriftnotifier [params]`

## Parameters
- `-h`: Show help message and exit
- `-c`: Path to the configuration file. Defaults to config.yaml

## License
Copyright (c) ShadowGuardAI
