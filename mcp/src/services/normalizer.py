import json
from typing import List, Dict, Any
from src.models.schemas import FindingCreate

class BaseNormalizer:
    def normalize(self, content: str) -> List[FindingCreate]:
        raise NotImplementedError

class SarifNormalizer(BaseNormalizer):
    def normalize(self, content: str) -> List[FindingCreate]:
        """Xử lý định dạng SARIF (Semgrep, CodeQL)"""
        data = json.loads(content)
        findings = []
        for run in data.get("runs", []):
            tool_name = run.get("tool", {}).get("driver", {}).get("name", "Unknown")
            for result in run.get("results", []):
                # Lấy vị trí file và dòng code
                locations = result.get("locations", [])
                file_path = "unknown"
                line_number = 0
                if locations:
                    phys_loc = locations[0].get("physicalLocation", {})
                    file_path = phys_loc.get("artifactLocation", {}).get("uri", "unknown")
                    line_number = phys_loc.get("region", {}).get("startLine", 0)

                findings.append(FindingCreate(
                    tool=tool_name,
                    rule_id=result.get("ruleId", "unknown"),
                    severity=result.get("level", "warning"),
                    message=result.get("message", {}).get("text", ""),
                    file_path=file_path,
                    line_number=line_number,
                    raw_data=result
                ))
        return findings

class NormalizerFactory:
    @staticmethod
    def get_normalizer(file_name: str) -> BaseNormalizer:
        if file_name.endswith(".sarif") or file_name.endswith(".json"):
            return SarifNormalizer()
        # Có thể thêm các Normalizer khác cho XML/SpotBugs ở đây
        return SarifNormalizer()