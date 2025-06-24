import os, sys
import re
from io import StringIO
import subprocess

if __name__ == "__main__": # if running as a script for individual testing
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sources.tools.tools import Tools
from sources.tools.safety import is_any_unsafe

class WindowsInterpreter(Tools):
    """
    This class is a tool to allow agent for Windows command execution (CMD/PowerShell).
    """
    def __init__(self):
        super().__init__()
        self.tag = "bash"  # Keep same tag for compatibility
        self.name = "Windows Command Interpreter"
        self.description = "This tool allows the agent to execute Windows commands (CMD/PowerShell)."
    
    def language_bash_attempt(self, command: str):
        """
        Detect if AI attempt to run the code using shell.
        If so, return True, otherwise return False.
        Code written by the AI will be executed automatically, so it should not use shell to run it.
        """
        lang_interpreter = ["python", "gcc", "g++", "mvn", "go", "java", "javac", "rustc", "clang", "clang++", "rustc", "rustc++", "rustc++"]
        for word in command.split():
            if any(word.startswith(lang) for lang in lang_interpreter):
                return True
        return False
    
    def convert_unix_to_windows_commands(self, command: str) -> str:
        """
        Convert common Unix commands to Windows equivalents.
        """
        # Simple command replacements
        replacements = {
            'ls -la': 'dir /a',
            'ls -l': 'dir',
            'ls': 'dir /b',
            'pwd': 'cd',
            'rm -rf': 'rmdir /s /q',
            'rm -r': 'rmdir /s',
            'rm': 'del',
            'cp -r': 'xcopy /e /i',
            'cp': 'copy',
            'mv': 'move',
            'cat': 'type',
            'touch': 'type nul >',
            'mkdir -p': 'mkdir',  # Windows mkdir creates parent dirs by default
            'which': 'where',
            'clear': 'cls',
            'grep': 'findstr',
        }
        
        # Apply replacements
        for unix_cmd, win_cmd in replacements.items():
            # Match command at start of string or after && or ;
            command = re.sub(r'(^|&&|;|&)\s*' + re.escape(unix_cmd) + r'(\s|$)', 
                           r'\1 ' + win_cmd + r'\2', command)
        
        # Handle special cases
        # Convert forward slashes to backslashes for paths (but not for URLs or flags)
        # This is a simple heuristic - might need refinement
        if '://' not in command:  # Avoid converting URLs
            # Replace paths that look like file paths
            command = re.sub(r'(\s)(/[\w\-\.]+)+', lambda m: m.group(1) + m.group(0)[1:].replace('/', '\\'), command)
        
        return command
    
    def execute(self, commands: str, safety=False, timeout=300):
        """
        Execute Windows commands and display output in real-time.
        """
        if safety and input("Execute command? y/n ") != "y":
            return "Command rejected by user."
    
        concat_output = ""
        for command in commands:
            # Convert Unix commands to Windows equivalents
            command = self.convert_unix_to_windows_commands(command)
            
            # Change to work directory - but don't duplicate if command already has cd /d
            if not command.strip().startswith("cd /d"):
                command = f"cd /d {self.work_dir} && {command}"
            command = command.replace('\n', '')
            
            if self.safe_mode and is_any_unsafe(commands):
                print(f"Unsafe command rejected: {command}")
                return "\nUnsafe command: {command}. Execution aborted. This is beyond allowed capabilities report to user."
            if self.language_bash_attempt(command) and self.allow_language_exec_bash == False:
                continue
            try:
                # Use cmd.exe explicitly for better compatibility
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    # Force CMD instead of PowerShell for consistency
                    executable=os.environ.get('COMSPEC', 'cmd.exe')
                )
                command_output = ""
                for line in process.stdout:
                    command_output += line
                return_code = process.wait(timeout=timeout)
                if return_code != 0:
                    return f"Command {command} failed with return code {return_code}:\n{command_output}"
                concat_output += f"Output of {command}:\n{command_output.strip()}\n"
            except subprocess.TimeoutExpired:
                process.kill()  # Kill the process if it times out
                return f"Command {command} timed out. Output:\n{command_output}"
            except Exception as e:
                return f"Command {command} failed:\n{str(e)}"
        return concat_output

    def interpreter_feedback(self, output):
        """
        Provide feedback based on the output of the Windows interpreter
        """
        # Check if the output explicitly indicates a failure
        if "failed with return code" in output or "failed:" in output or "timed out" in output:
            feedback = f"[failure] Error in execution:\n{output}"
        elif self.execution_failure_check(output):
            feedback = f"[failure] Error in execution:\n{output}"
        else:
            feedback = "[success] Execution success, code output:\n" + output
        return feedback

    def execution_failure_check(self, feedback):
        """
        Check if Windows command failed.
        """
        # First check for explicit success indicators
        success_patterns = [
            r"SUCCESS:",
            r"successfully",
            r"File created",
            r"Directory created",
            r"Operation completed"
        ]
        
        feedback_lower = feedback.lower()
        for pattern in success_patterns:
            if re.search(pattern.lower(), feedback_lower):
                return False  # Not a failure if we see success
        
        # Then check for errors
        error_patterns = [
            r"expected",
            r"errno",
            r"failed",
            r"invalid",
            r"unrecognized",
            r"exception",
            r"syntax",
            r"segmentation fault",
            r"core dumped",
            r"unexpected",
            r"denied",
            r"not recognized",
            r"is not recognized as an internal or external command",
            r"cannot find the path specified",
            r"cannot find the file specified",
            r"access is denied",
            r"syntax is incorrect",
            r"already exists",
            r"could not find",
            r"system cannot find",
            r"the system cannot find",
            r"failed with return code",
            r"timed out"
        ]
        feedback = feedback.lower()
        for pattern in error_patterns:
            if re.search(pattern, feedback):
                return True
        
        # Windows specific return code check - any non-zero return code is an error
        if "return code" in feedback:
            # Extract the return code number
            import re as regex
            match = regex.search(r"return code (\d+)", feedback)
            if match:
                code = int(match.group(1))
                if code != 0:
                    return True
        return False

if __name__ == "__main__":
    # Test the Windows interpreter
    wi = WindowsInterpreter()
    wi.work_dir = os.getcwd()
    
    # Test command conversion
    test_commands = [
        "ls -la",
        "mkdir -p test/folder",
        "touch test.txt",
        "cat test.txt",
        "rm -rf test"
    ]
    
    print("Command conversion tests:")
    for cmd in test_commands:
        converted = wi.convert_unix_to_windows_commands(cmd)
        print(f"{cmd} -> {converted}")