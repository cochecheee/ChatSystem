import os
import httpx
import zipfile
import io
from typing import List, Dict, Any

class GitHubClient:
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def fetch_artifact(self, owner: str, repo: str, artifact_id: int) -> List[Dict[str, Any]]:
        """Tải artifact từ GitHub, giải nén và lọc các file .sarif hoặc .json"""
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, follow_redirects=True)
            if response.status_code != 200:
                print(f"❌ Lỗi khi tải artifact: {response.status_code}")
                return []

            # Giải nén file ZIP trong bộ nhớ (memory)
            results = []
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                for file_name in z.namelist():
                    # Chỉ lấy các file kết quả bảo mật
                    if file_name.endswith(('.sarif', '.json', '.xml')):
                        with z.open(file_name) as f:
                            content = f.read().decode("utf-8")
                            results.append({"file_name": file_name, "content": content})
            
            print(f"✅ Đã tải và giải nén {len(results)} file từ artifact {artifact_id}")
            return results

    async def get_run_artifacts(self, owner: str, repo: str, run_id: int):
        """Lấy danh sách ID của các artifact thuộc về một run cụ thể"""
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json().get("artifacts", [])
            return []

    async def get_workflow_runs(self, owner: str, repo: str, workflow_name: str):
        """Lấy danh sách các lần chạy workflow (Dùng cho Poller ở Plan 04)"""
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code == 200:
                runs = response.json().get("workflow_runs", [])
                # Lọc theo tên workflow (ví dụ: 'Security Scans')
                return [r for r in runs if r.get("name") == workflow_name]
            return []
        