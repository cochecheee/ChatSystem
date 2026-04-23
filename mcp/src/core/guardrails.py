import re
from detect_secrets import SecretsCollection
from detect_secrets.settings import default_settings

class ScrubbingService:
    def __init__(self):
        # Các mẫu Regex để tìm PII (Thông tin cá nhân - REQ-2.4)
        self.pii_patterns = {
            "email": r'[\w\.-]+@[\w\.-]+\.\w+',
            "ip_address": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
        }

    def scrub_content(self, content: str) -> str:
        """Làm sạch nội dung: Xóa Secrets và PII (Plan 02-02, Task 2)"""
        if not content: return ""
        scrubbed = content

        # 1. Xóa PII (Emails, IPs) bằng Regex
        for label, pattern in self.pii_patterns.items():
            scrubbed = re.sub(pattern, f"[PII_{label.upper()}_SCRUBBED]", scrubbed)
        
        # 2. Xóa Secrets (API Keys, Tokens) bằng Regex cũ của bạn (Mapping truths REQ-2.3)
        api_key_pattern = r'(?:key|token|secret|password|auth|pwd)[^\s]*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{16,})["\']?'
        scrubbed = re.sub(api_key_pattern, "[SECRET_SCRUBBED]", scrubbed)

        return scrubbed

class InjectionGuardrail:
    def __init__(self):
        # Danh sách đen chặn Prompt Injection (Plan 02-02, Task 3)
        self.blacklist = [
            "ignore previous instructions", 
            "system prompt", 
            "you are now a chat bot",
            "jailbreak",
            "<script>",
            "system.exit"
        ]
        self.max_length = 10000 # Giới hạn độ dài để tránh DoS (T-02-09)

    def validate_finding(self, message: str) -> bool:
        """Kiểm tra nội dung lỗi có an toàn để đưa vào AI không (REQ-2.4)"""
        if not message: return True
        
        # Kiểm tra độ dài (REQ-2.5)
        if len(message) > self.max_length:
            print("⚠️ Finding message too long, rejected by Guardrail.")
            return False

        lowered_message = message.lower()
        for item in self.blacklist:
            if item in lowered_message:
                print(f"🚫 Prompt Injection attempt detected: {item}")
                return False 
        return True