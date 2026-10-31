import argparse
import time
import logging
import os
import yaml
import json
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import smtplib
from email.mime.text import MIMEText

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

# Define constants
DEFAULT_CONFIG_FILE = 'config.yaml'

# --- Helper Functions ---

def load_config(config_file):
    """
    Loads configuration from a YAML file.

    Args:
        config_file (str): Path to the configuration file.

    Returns:
        dict: Configuration data.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        YAMLError: If the configuration file is not valid YAML.
    """
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
            return config
    except FileNotFoundError:
        logging.error(f"Configuration file not found: {config_file}")
        raise
    except yaml.YAMLError as e:
        logging.error(f"Error parsing configuration file: {e}")
        raise

def validate_config(config):
    """
    Validates the loaded configuration data.  Basic validation.  Expand as needed.

    Args:
        config (dict): Configuration data to validate.

    Returns:
        bool: True if the configuration is valid, False otherwise.  Raises exception on invalid config.

    Raises:
        ValueError: If required configuration parameters are missing or invalid.
    """
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a dictionary.")

    if 'monitored_files' not in config or not isinstance(config['monitored_files'], list):
        raise ValueError("Configuration must include 'monitored_files' as a list.")

    if not config['monitored_files']:
        raise ValueError("Configuration must name at least one file in 'monitored_files'; an empty list watches nothing.")

    if 'notification' not in config or not isinstance(config['notification'], dict):
        raise ValueError("Configuration must include 'notification' settings.")

    if config['notification'].get('type') not in ('email', 'slack', None):
        raise ValueError("Notification type must be 'email' or 'slack', or None.")

    if config['notification'].get('type') == 'email':
        email_config = config['notification'].get('email')
        if not email_config:
            raise ValueError("Email configuration is required when notification type is email.")

        required_email_fields = ['sender', 'recipients', 'smtp_server', 'smtp_port']
        for field in required_email_fields:
            if field not in email_config or not email_config[field]:
                raise ValueError(f"Missing or empty email configuration field: {field}")
    # Add more validation rules as needed (e.g., slack validation)
    return True

def send_email_alert(subject, body, config):
    """
    Sends an email alert.

    Args:
        subject (str): Email subject.
        body (str): Email body.
        config (dict): Configuration data containing email settings.
    """
    email_config = config['notification']['email']
    sender = email_config['sender']
    recipients = email_config['recipients']
    smtp_server = email_config['smtp_server']
    smtp_port = email_config['smtp_port']
    smtp_user = email_config.get('smtp_user')
    # The password comes from an environment variable, never from the
    # config file. Name the variable with smtp_password_env, or use the
    # default name SMTP_PASSWORD.
    password_env = email_config.get('smtp_password_env') or 'SMTP_PASSWORD'
    smtp_password = os.environ.get(password_env)

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            if server.has_extn('STARTTLS'):
                # Use transport encryption whenever the server offers
                # it, whether or not a login follows. If it cannot be
                # established, the alert is not sent in clear.
                server.starttls()
                server.ehlo()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.sendmail(sender, recipients, msg.as_string())
        logging.info("Email alert sent successfully.")
    except Exception as e:
        logging.error(f"Error sending email alert: {e}")


def send_slack_alert(message, config):
    """
    Placeholder for sending Slack alerts.  Implement Slack integration here.

    Args:
        message (str): The message to send to Slack.
        config (dict): The configuration.
    """
    # TODO: Implement Slack integration using the Slack API or a library like `slack_sdk`.
    logging.warning("Slack integration not implemented yet.  Message: %s", message)
    print(f"Slack Alert (Not Implemented): {message}")  # For demonstration purposes

def lint_file(filepath, filetype):
    """
    Lints a file based on its file type using yamllint or jsonlint.

    Args:
        filepath (str): The path to the file.
        filetype (str): The file type (e.g., "yaml", "json").

    Returns:
        tuple: (True, None) if linting is successful, (False, error_message) if there's an error.
        A missing linter returns (None, error_message): that is a tool
        problem on this machine, not a verdict on the file.
    """
    try:
        if filetype == "yaml":
            result = subprocess.run(['yamllint', filepath], capture_output=True, text=True, check=True)
            if result.returncode == 0:
                return True, None
            else:
                return False, f"yamllint failed with error: {result.stderr}"
        elif filetype == "json":
            result = subprocess.run(['jsonlint', filepath], capture_output=True, text=True, check=True)
            if result.returncode == 0:
                return True, None
            else:
                return False, f"jsonlint failed with error: {result.stderr}"
        else:
            return False, f"Unsupported file type: {filetype}"
    except FileNotFoundError as e:
        return None, f"Linter not found. Ensure yamllint/jsonlint is installed: {e}"
    except subprocess.CalledProcessError as e:
        return False, f"Linter process error: {e.stderr}"
    except Exception as e:
        return False, f"An unexpected error occurred during linting: {e}"

# --- Event Handler ---

class ConfigChangeHandler(FileSystemEventHandler):
    """
    Handles file system events, specifically configuration file changes.
    """

    def __init__(self, config):
        super().__init__()
        self.config = config
        # Resolve monitored paths once, so a relative entry in the
        # config matches the absolute paths watchdog reports.
        self.monitored_files = [os.path.realpath(os.path.abspath(p)) for p in config.get('monitored_files', [])]

    def on_modified(self, event):
        """
        Called when a file or directory is modified.

        Args:
            event (watchdog.events.FileSystemEvent): The event object representing the file system event.
        """
        if event.is_directory:
            return  # Ignore directory changes

        filepath = event.src_path
        resolved = os.path.realpath(os.path.abspath(filepath))

        if resolved in self.monitored_files:
            logging.info(f"Configuration file changed: {filepath}")

            if filepath.endswith(('.yaml', '.yml')):
                filetype = "yaml"
            elif filepath.endswith('.json'):
                filetype = "json"
            else:
                filetype = "unknown"

            if filetype not in ("yaml", "json"):
                # No linter applies here. Send a plain modified alert
                # instead of failing on an unassigned lint result.
                self.send_alert(f"Configuration file {filepath} has been modified.")
                return

            lint_success, lint_message = lint_file(filepath, filetype)

            if lint_success is None:
                # The linter itself is missing on this machine. That
                # says nothing about the file, so log it locally and
                # do not report the file as invalid to recipients.
                logging.error(f"Linting skipped for {filepath}: {lint_message}")
                return

            if not lint_success:
                error_message = f"Configuration file {filepath} is invalid: {lint_message}"
                logging.error(error_message)
                self.send_alert(error_message)
                return

            try:
                message = f"Configuration file {filepath} has been modified. Linting: {lint_success}.  Message: {lint_message if lint_message else 'Linting Passed'}"
                self.send_alert(message)

            except Exception as e:
                logging.error(f"Error processing file change: {e}")

    def send_alert(self, message):
        """
        Sends an alert based on the configured notification method.

        Args:
            message (str): The alert message.
        """
        notification_type = self.config['notification'].get('type')

        if notification_type == 'email':
            send_email_alert("Configuration Drift Detected", message, self.config)
        elif notification_type == 'slack':
            send_slack_alert(message, self.config) # Call Slack Function
        else:
            logging.warning("No notification method configured.")


# --- Argument Parsing ---

def setup_argparse():
    """
    Sets up the argument parser for the command-line interface.

    Returns:
        argparse.ArgumentParser: The argument parser.
    """
    parser = argparse.ArgumentParser(description="Monitors configuration files for changes and sends alerts.")
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG_FILE,
                        help="Path to the configuration file. Defaults to config.yaml")
    return parser

# --- Main Function ---

def main():
    """
    Main function to start the configuration drift notifier.
    """
    parser = setup_argparse()
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        validate_config(config) # Validate after loading.
    except Exception as e:
        print(f"Configuration error: {e}")
        exit(1)


    # Resolve each monitored path to its absolute form and watch the
    # file the operator named, wherever it lives. Paths are never
    # rewritten to a different file inside the working directory.
    config['monitored_files'] = [os.path.realpath(os.path.abspath(p)) for p in config['monitored_files']]

    event_handler = ConfigChangeHandler(config)
    observer = Observer()

    # Determine the directories to watch
    directories_to_watch = set()
    for file_path in config['monitored_files']:
        directories_to_watch.add(os.path.dirname(os.path.abspath(file_path)))

    for directory in directories_to_watch:
       observer.schedule(event_handler, directory, recursive=False)

    observer.start()

    try:
        while True:
            time.sleep(1)  # Check for interrupt every second
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# --- Run the main function ---

if __name__ == "__main__":
    main()


"""
Usage Examples:

1.  Basic Usage:
    python main.py

    Assumes a config.yaml file exists in the same directory.

2.  Specifying a Configuration File:
    python main.py -c my_config.yaml

    Uses the my_config.yaml file for configuration.

3. Email example config
notification:
  type: email
  email:
    sender: "sender@example.com"
    recipients: ["recipient1@example.com", "recipient2@example.com"]
    smtp_server: "smtp.example.com"
    smtp_port: 587
    smtp_user: "smtp_username" #Optional
    # No password field here. Set the SMTP_PASSWORD environment
    # variable, or name a different variable with smtp_password_env.

4.  Slack Placeholder example config
notification:
  type: slack

monitored_files:
  - "config.yaml"
  - "another_config.json"
"""