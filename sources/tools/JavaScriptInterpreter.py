import os, sys
import re
from io import StringIO
import subprocess

if __name__ == "__main__": # if running as a script for individual testing
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sources.tools.tools import Tools
from sources.tools.safety import is_any_unsafe

class JavaScriptInterpreter(Tools):
    """
    This class is a tool to allow agent for JavaScript code compilation and execution.
    """
    def __init__(self):
        super().__init__()
        self.tag = "javascript"
        self.name = "JavaScript Interpreter"
        self.description = "This tool allows the agent to execute JavaScript code using Node.js."
    
    def execute(self, blocks: [str], safety=False):
        """
        Execute JavaScript code blocks using Node.js.
        Args:
            blocks: List of JavaScript code blocks to execute
            safety: Whether to ask for user confirmation before execution
        Returns:
            str: The output from executing the JavaScript code
        """
        if safety:
            for block in blocks:
                if input(f"Execute JavaScript code? y/n ") != "y":
                    return "JavaScript code execution rejected by user."
        
        concat_output = ""
        for block in blocks:
            if self.safe_mode and is_any_unsafe(block):
                print(f"Unsafe JavaScript code rejected: {block}")
                return "\nUnsafe JavaScript code. Execution aborted. This is beyond allowed capabilities report to user."
            
            try:
                # Write the JavaScript code to a temporary file
                temp_file = os.path.join(self.work_dir, "temp_script.js")
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write(block)
                
                # Execute the JavaScript file using Node.js
                result = subprocess.run(
                    ["node", temp_file],
                    cwd=self.work_dir,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                # Clean up the temporary file
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                
                if result.returncode != 0:
                    concat_output += f"JavaScript execution error:\n{result.stderr}\n"
                else:
                    concat_output += result.stdout
                    if result.stderr:
                        concat_output += f"\nWarnings:\n{result.stderr}"
                        
            except subprocess.TimeoutExpired:
                concat_output += "JavaScript execution timed out after 30 seconds.\n"
            except FileNotFoundError:
                concat_output += "Node.js is not installed or not in PATH. Please install Node.js to execute JavaScript code.\n"
            except Exception as e:
                concat_output += f"JavaScript execution failed: {str(e)}\n"
        
        return concat_output
    
    def interpreter_feedback(self, output):
        """
        Provide feedback to the AI based on the JavaScript execution output.
        """
        if self.execution_failure_check(output):
            feedback = f"[failure] JavaScript execution error:\n{output}"
        else:
            feedback = "[success] JavaScript executed successfully:\n" + output
        return feedback
    
    def execution_failure_check(self, output):
        """
        Check if JavaScript execution failed based on the output.
        """
        error_indicators = [
            "error:",
            "Error:",
            "ERROR:",
            "SyntaxError",
            "ReferenceError",
            "TypeError", 
            "RangeError",
            "EvalError",
            "URIError",
            "execution failed",
            "not installed",
            "not in PATH",
            "timed out"
        ]
        
        output_lower = output.lower()
        for indicator in error_indicators:
            if indicator.lower() in output_lower:
                return True
        
        return False

if __name__ == "__main__":
    # Test the JavaScript interpreter
    js = JavaScriptInterpreter()
    js.work_dir = os.getcwd()
    
    # Test code
    test_code = '''
console.log("Hello from JavaScript!");
const arr = [1, 2, 3, 4, 5];
const doubled = arr.map(x => x * 2);
console.log("Original:", arr);
console.log("Doubled:", doubled);
'''
    
    print("Testing JavaScript interpreter...")
    output = js.execute([test_code])
    print(output)
    print("\nFeedback:", js.interpreter_feedback(output))