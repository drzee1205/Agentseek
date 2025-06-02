#!/bin/bash

install_chromedriver() {
    # Detect Chrome version
    if command -v google-chrome >/dev/null 2>&1; then
        CHROME_VERSION=$(google-chrome --version | awk '{print $3}')
    elif command -v google-chrome-stable >/dev/null 2>&1; then
        CHROME_VERSION=$(google-chrome-stable --version | awk '{print $3}')
    else
        echo "❌ Google Chrome is not installed or not in PATH."
        return 1
    fi

    echo "🔍 Detected Chrome version: $CHROME_VERSION"

    # Construct download URL
    DRIVER_NAME="chromedriver-linux64"
    ZIP_URL="https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/${DRIVER_NAME}.zip"

    echo "🌐 Downloading ChromeDriver from: $ZIP_URL"

    # Remove any older downloads
    rm -rf /tmp/"${DRIVER_NAME}.zip" /tmp/"${DRIVER_NAME}"

    # Download
    curl -fLo "${DRIVER_NAME}.zip" "$ZIP_URL" || {
        echo "❌ Failed to download ChromeDriver for version $CHROME_VERSION"
        return 1
    }

    echo "📦 Unzipping..."
    unzip -q /tmp/"${DRIVER_NAME}.zip" -d /tmp

    echo "🚀 Installing to /usr/local/bin..."
    sudo mv /tmp/"${DRIVER_NAME}/chromedriver" /usr/local/bin/chromedriver
    sudo chmod +x /usr/local/bin/chromedriver

    # Clean up
    rm -rf /tmp/"${DRIVER_NAME}.zip" /tmp/"${DRIVER_NAME}"

    # Verify
    echo "✅ Installed ChromeDriver version:"
    chromedriver --version
    return 0
}

echo "Starting installation for Linux..."

set -e

if ! command -v python3.10 &> /dev/null; then
    echo "Error: Python 3.10 is not installed. Please install Python 3.10 and try again."
    echo "You can install it using: sudo apt-get install python3.10 python3.10-dev python3.10-venv"
    exit 1
fi

# Check if pip3.10 is available
if ! python3.10 -m pip --version &> /dev/null; then
    echo "Error: pip for Python 3.10 is not installed. Installing python3.10-pip..."
    sudo apt-get install -y python3.10-pip || { echo "Failed to install python3.10-pip"; exit 1; }
fi

# Update package list
sudo apt-get update || { echo "Failed to update package list"; exit 1; }
# make sure essential tool are installed
sudo apt-get install -y \
    python3-dev \
    python3-pip \
    python3-wheel \
    build-essential \
    alsa-utils \
    portaudio19-dev \
    python3-pyaudio \
    libgtk-3-dev \
    libnotify-dev \
    libgconf-2-4 \
    libnss3 \
    libxss1 || { echo "Failed to install packages"; exit 1; }

# Install ChromeDriver matching Chrome browser version
install_chromedriver
if [[ $? -ne 0 ]]; then
    echo "⚠️ Need to install ChromeDriver manually..."
fi

# Upgrade pip for Python 3.10
python3.10 -m pip install --upgrade pip || { echo "Failed to upgrade pip"; exit 1; }
# Install and upgrade setuptools and wheel
python3.10 -m pip install --upgrade setuptools wheel || { echo "Failed to install setuptools and wheel"; exit 1; }
# Install Selenium for chromedriver
python3.10 -m pip install selenium || { echo "Failed to install selenium"; exit 1; }
# Install Python dependencies from requirements.txt
python3.10 -m pip install -r requirements.txt --no-cache-dir || { echo "Failed to install requirements.txt"; exit 1; }
# install docker compose
sudo apt install -y docker-compose

echo "Installation complete for Linux!"