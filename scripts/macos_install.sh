#!/bin/bash

install_chromedriver() {
    # Detect Chrome version
    if [[ -e "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]]; then
        CHROME_VERSION=$("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version | awk '{print $3}')
    else
        echo "❌ Google Chrome is not installed in the default location."
        return 1
    fi

    echo "🔍 Detected Chrome version: $CHROME_VERSION"

    # Detect architecture
    ARCH=$(uname -m)
    if [[ "$ARCH" == "arm64" ]]; then
        PLATFORM="mac-arm64"
    elif [[ "$ARCH" == "x86_64" ]]; then
        PLATFORM="mac-x64"
    else
        echo "❌ Unsupported architecture: $ARCH"
        return 1
    fi

    DRIVER_NAME="chromedriver-${PLATFORM}"
    ZIP_URL="https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/${PLATFORM}/${DRIVER_NAME}.zip"

    echo "🌐 Downloading ChromeDriver from: $ZIP_URL"

    # Remove any older downloads
    rm -rf /tmp/"${DRIVER_NAME}.zip" /tmp/"${DRIVER_NAME}"

    # Download
    curl -fLo /tmp/"${DRIVER_NAME}.zip" "$ZIP_URL" || {
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

echo "Starting installation for macOS..."

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

# Check if homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# update
brew update
# make sure wget installed
brew install wget

# Install ChromeDriver matching Chrome browser version
install_chromedriver
if [[ $? -ne 0 ]]; then
    echo "⚠️ Falling back to Homebrew installation of latest ChromeDriver..."
    # Install chromedriver using Homebrew
    brew install --cask chromedriver
    echo "✅ Installed latest ChromeDriver via Homebrew:"
    chromedriver --version
fi

# Install portaudio for pyAudio using Homebrew
brew install portaudio

# Upgrade pip for Python 3.10
python3.10 -m pip install --upgrade pip || { echo "Failed to upgrade pip"; exit 1; }
# Install and upgrade setuptools and wheel
python3.10 -m pip install --upgrade setuptools wheel || { echo "Failed to install setuptools and wheel"; exit 1; }
# Install Selenium for chromedriver
python3.10 -m pip install selenium || { echo "Failed to install selenium"; exit 1; }
# Install Python dependencies from requirements.txt
python3.10 -m pip install -r requirements.txt --no-cache-dir || { echo "Failed to install requirements.txt"; exit 1; }

echo "Installation complete for macOS!"