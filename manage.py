#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path


def load_dotenv():
    env_file = Path(__file__).resolve().parent / '.env'
    if env_file.exists():
        with open(env_file, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())


def main():
    """Run administrative tasks."""
    load_dotenv()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_lead.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
