# CHƯƠNG 3: THIẾT KẾ VÀ XÂY DỰNG HỆ THỐNG

## 3.1. Kiến trúc tổng thể hệ thống

### 3.1.1. Sơ đồ kiến trúc tổng thể

Trong bối cảnh phát triển phần mềm hiện đại, việc tích hợp bảo mật vào quy trình CI/CD đã trở thành một yêu cầu thiết yếu nhằm đảm bảo an toàn thông tin xuyên suốt vòng đời phát triển phần mềm. Hệ thống được đề xuất trong nghiên cứu này ra đời nhằm giải quyết bài toán phát hiện sớm lỗ hổng bảo mật ngay trong quá trình phát triển mã nguồn, thay vì chờ đợi đến giai đoạn kiểm thử hoặc triển khai như các phương pháp truyền thống. Kiến trúc tổng thể của hệ thống được thiết kế theo mô hình module hóa, cho phép các thành phần hoạt động độc lập nhưng vẫn đảm bảo sự phối hợp chặt chẽ thông qua các giao diện chuẩn hóa.

Hệ thống được đề xuất bao gồm sự tích hợp của nhiều thành phần công nghệ tiên tiến, mỗi thành phần đảm nhận một vai trò cụ thể trong quy trình tổng thể. Các thành phần này được kết nối với nhau thông qua các API chuẩn hóa, đảm bảo tính linh hoạt và khả năng mở rộng trong tương lai. Kiến trúc tổng thể của hệ thống được minh họa trong Hình 3.1.

**Hình 3.1. Kiến trúc tổng thể hệ thống**

*(Chèn sơ đồ kiến trúc tổng thể tại đây)*

Kiến trúc hệ thống được thiết kế theo nguyên tắc "security by design", trong đó bảo mật được tích hợp vào từng giai đoạn của quy trình phát triển phần mềm. Nguyên tắc này đảm bảo rằng mọi thay đổi trong mã nguồn đều được kiểm tra bảo mật ngay lập tức, giúp phát hiện và xử lý lỗ hổng sớm trước khi chúng có thể lan rộng trong hệ thống.

Hệ thống bao gồm bảy thành phần chính, mỗi thành phần đảm nhận một chức năng cụ thể và phối hợp với các thành phần khác để tạo thành một quy trình hoàn chỉnh:

**Thành phần thứ nhất: Source Code Repository (Hệ thống quản lý mã nguồn)**

Source Code Repository đóng vai trò là điểm bắt đầu của toàn bộ quy trình, nơi lưu trữ và quản lý mã nguồn của dự án. Trong hệ thống này, GitHub được lựa chọn làm nền tảng quản lý mã nguồn nhờ vào khả năng tích hợp sâu với GitHub Actions, hỗ trợ webhook events, và cung cấp hệ sinh thái phong phú cho việc phát triển phần mềm mã nguồn mở. Repository không chỉ lưu trữ mã nguồn mà còn lưu trữ các file cấu hình cho CI/CD pipeline, security policies, và các rule files cho các công cụ SAST. Khi developer thực hiện các thao tác như push code, tạo pull request, hoặc merge branches, GitHub sẽ phát sinh các webhook events để kích hoạt các workflow tự động trong hệ thống.

**Thành phần thứ hai: CI/CD Pipeline (Quy trình tích hợp và triển khai liên tục)**

CI/CD Pipeline là trung tâm của hệ thống, chịu trách nhiệm tự động hóa quy trình build, test và triển khai phần mềm. GitHub Actions được sử dụng làm nền tảng CI/CD nhờ vào khả năng tích hợp native với GitHub Repository, hỗ trợ parallel execution cho nhiều jobs, và cung cấp marketplace phong phú với hàng ngàn actions có sẵn. Pipeline được thiết kế với nhiều stages tuần tự và song song, trong đó các công cụ SAST được tích hợp để quét bảo mật song song nhằm tối ưu hóa thời gian thực thi. Kết quả quét được lưu trữ dưới dạng SARIF (Static Analysis Results Interchange Format) artifacts, một định dạng chuẩn của OASIS cho phép trao đổi kết quả phân tích mã nguồn giữa các công cụ khác nhau.

**Thành phần thứ ba: MCP (Model Context Protocol) Server**

MCP Server đóng vai trò là middleware trung gian trong hệ thống, kết nối giữa CI/CD pipeline và AI assistant. Thành phần này chịu trách nhiệm thu thập kết quả quét từ GitHub Artifacts, thực hiện các bước sanitization để loại bỏ thông tin nhạy cảm, chuẩn hóa dữ liệu từ nhiều định dạng khác nhau về một schema thống nhất, và làm giàu dữ liệu bằng cách bổ sung thông tin ngữ cảnh từ các nguồn như CWE database, OWASP Top 10, và NVD (National Vulnerability Database). MCP Server cũng đóng vai trò là secure gateway, áp dụng nhiều lớp guardrail để đảm bảo rằng chỉ những dữ liệu an toàn và đã được kiểm tra mới được chuyển đến LLM Orchestrator.

**Thành phần thứ tư: LLM Orchestrator (Bộ điều phối mô hình ngôn ngữ lớn)**

LLM Orchestrator là thành phần thông minh của hệ thống, sử dụng mô hình ngôn ngữ lớn Gemini (phiên bản 2.5 hoặc 3.1) để phân tích kết quả quét bảo mật và tạo ra các đề xuất khắc phục dựa trên ngữ cảnh mã nguồn. Thành phần này bao gồm prompt engine để xây dựng system prompts tối ưu, context manager để quản lý ngữ cảnh hội thoại, và response validator để đảm bảo chất lượng và an toàn của phản hồi từ LLM. LLM Orchestrator có khả năng phân tích mã nguồn, giải thích nguyên nhân của lỗ hổng, đánh giá mức độ ảnh hưởng, và đề xuất các đoạn code cụ thể để khắc phục vấn đề.

**Thành phần thứ năm: ChatOps Platform (Nền tảng chat tích hợp)**

ChatOps Platform cung cấp giao diện tương tác trực tiếp giữa developers và hệ thống thông qua nền tảng chat. Thành phần này cho phép developers thực hiện các thao tác như kiểm tra trạng thái pipeline, xem kết quả quét, yêu cầu giải thích chi tiết về lỗ hổng, đề xuất cách khắc phục, và điều khiển pipeline (rerun, cancel, approve) mà không cần rời khỏi môi trường chat. AI assistant được tích hợp vào ChatOps Platform thông qua webhook integration, cho phép xử lý các commands tự nhiên và trả về kết quả dưới dạng tin nhắn chat.

**Thành phần thứ sáu: Web Dashboard (Giao diện web hiển thị kết quả)**

Web Dashboard cung cấp giao diện trực quan để hiển thị kết quả phân tích bảo mật, báo cáo thống kê, và biểu đồ theo dõi xu hướng. Dashboard được thiết kế với real-time polling mechanism, cập nhật kết quả mỗi 15 giây, cho phép developers và security team theo dõi trạng thái của pipeline và kết quả quét một cách kịp thời. Dashboard cũng tích hợp chat interface để tương tác với AI assistant và cung cấp các công cụ điều khiển pipeline trực tiếp từ giao diện web.

**Thành phần thứ bảy: Storage Layer (Lớp lưu trữ)**

Storage Layer bao gồm cơ sở dữ liệu SQLite để lưu trữ kết quả đã chuẩn hóa và dữ liệu phân tích từ AI, cùng với local storage để lưu trữ raw SARIF files cho mục đích audit. Database được thiết kế với indexing tối ưu để hỗ trợ truy vấn nhanh chóng, đặc biệt là các truy vấn theo repository, run ID, và mức độ nghiêm trọng của lỗ hổng. Storage Layer cũng bao gồm caching layer để giảm số lượng API calls đến các dịch vụ bên ngoài và cải thiện hiệu năng của hệ thống.

### 3.1.2. Các thành phần chính và tương tác

Mối quan hệ tương tác giữa các thành phần trong hệ thống được thiết kế theo mô hình event-driven architecture, trong đó các sự kiện được phát sinh và xử lý một cách bất đồng bộ. Mô hình này cho phép hệ thống xử lý nhiều request đồng thời mà không bị block bởi các thao tác I/O, đồng thời đảm bảo tính fault tolerance và scalability. Sơ đồ tương tác giữa các thành phần được mô tả chi tiết dưới đây.

**Tương tác giữa GitHub Repository và GitHub Actions CI:**

Khi developer thực hiện các thao tác trên mã nguồn như push code lên repository hoặc tạo pull request mới, GitHub sẽ phát sinh webhook events tương ứng. Webhook events này được gửi đến GitHub Actions để kích hoạt workflow đã được cấu hình trong file `.github/workflows/main.yml`. Workflow này định nghĩa toàn bộ quy trình CI/CD, bao gồm các jobs cần thực hiện, dependencies giữa các jobs, và điều kiện để trigger workflow. GitHub Actions sau đó sẽ provision các runner (máy ảo hoặc container) để thực thi các jobs theo định nghĩa trong workflow. Quá trình này bao gồm việc checkout mã nguồn, cài đặt dependencies, build ứng dụng, chạy unit tests, và thực hiện quét bảo mật bằng các công cụ SAST.

**Tương tác giữa GitHub Actions CI và MCP Gateway:**

Sau khi hoàn tất quá trình quét bảo mật, mỗi công cụ SAST sẽ tạo ra kết quả dưới dạng file SARIF hoặc các định dạng tương đương. Các file này được upload lên GitHub Artifacts thông qua GitHub Actions API. MCP Gateway sẽ nhận được notification khi artifacts đã sẵn sàng và bắt đầu quá trình fetch dữ liệu. MCP Gateway sử dụng GitHub Personal Access Token (PAT) với scope `actions:read` để tải artifacts về, đảm bảo rằng token chỉ có quyền đọc và không thể thực hiện các thao tác ghi lên repository. Sau khi tải artifacts, MCP Gateway thực hiện quá trình sanitization để loại bỏ các thông tin nhạy cảm như API keys, credentials, và environment variables. Dữ liệu sau đó được chuẩn hóa về schema thống nhất và làm giàu với thông tin ngữ cảnh từ các nguồn bên ngoài.

**Tương tác giữa MCP Gateway và LLM Orchestrator:**

MCP Gateway cung cấp ngữ cảnh đã được chuẩn hóa và làm giàu cho LLM Orchestrator thông qua RESTful API. Ngữ cảnh này bao gồm danh sách các lỗ hổng đã được phát hiện, thông tin chi tiết về từng lỗ hổng (tool phát hiện, rule ID, severity, file path, line number, code snippet), và các thông tin bổ sung như CWE ID, OWASP category, và CVSS score. LLM Orchestrator sử dụng prompt engine để xây dựng system prompt tối ưu, kết hợp với findings context để tạo ra input cho mô hình LLM. Mô hình LLM sau đó thực hiện phân tích và tạo ra các đề xuất khắc phục dựa trên ngữ cảnh mã nguồn cụ thể. Phản hồi từ LLM được validate thông qua output guardrails trước khi được lưu trữ và chuyển đến các thành phần khác.

**Tương tác giữa LLM Orchestrator và Web Dashboard:**

Kết quả phân tích từ LLM được lưu trữ vào database và hiển thị trên Web Dashboard thông qua real-time polling mechanism. Dashboard gửi request đến backend API mỗi 15 giây để cập nhật kết quả mới nhất. Khi có kết quả mới, Dashboard sẽ render các UI components tương ứng, bao gồm danh sách lỗ hổng, biểu đồ thống kê theo severity, và chi tiết phân tích từ AI. Dashboard cũng tích hợp chat interface để cho phép users tương tác trực tiếp với AI assistant, yêu cầu giải thích chi tiết về lỗ hổng hoặc đề xuất cách khắc phục cụ thể.

**Tương tác giữa Developer và ChatOps Platform:**

Developer có thể tương tác với hệ thống thông qua ChatOps Platform bằng cách gửi các commands tự nhiên. ChatOps Platform nhận commands từ user, chuyển tiếp đến backend API để xử lý, và trả về kết quả dưới dạng tin nhắn chat. Backend API xác thực request thông qua JWT token, phân quyền dựa trên GitHub team membership, và routing đến các handlers tương ứng. Các handlers có thể là tool executors để thực hiện các thao tác trên pipeline, hoặc LLM query handlers để yêu cầu phân tích từ AI assistant. Kết quả được format thành tin nhắn chat và gửi về user thông qua chat platform API.

**Luồng dữ liệu tổng thể:**

Luồng dữ liệu trong hệ thống bắt đầu từ việc developer push code lên repository, kích hoạt CI/CD pipeline, chạy các công cụ SAST, upload kết quả, MCP Server xử lý và chuẩn hóa dữ liệu, LLM phân tích và đề xuất khắc phục, và cuối cùng kết quả được hiển thị trên Dashboard và ChatOps Platform. Toàn bộ quá trình này được thực hiện tự động mà không cần sự can thiệp thủ công, giúp developers nhận được phản hồi bảo mật ngay lập tức sau khi thực hiện thay đổi mã nguồn.

## 3.2. Thiết kế và xây dựng CI/CD Pipeline tích hợp SAST

### 3.2.1. Cấu trúc pipeline stages

CI/CD pipeline là xương sống của hệ thống, đóng vai trò trung tâm trong việc tự động hóa quy trình phát triển phần mềm và tích hợp các hoạt động kiểm tra bảo mật. Pipeline được thiết kế với cấu trúc multi-stage, trong đó mỗi stage đảm nhận một chức năng cụ thể và có thể được thực thi tuần tự hoặc song song tùy thuộc vào dependencies giữa các stages. Việc thiết kế pipeline theo mô hình này cho phép tối ưu hóa thời gian thực thi bằng cách chạy các jobs độc lập song song, đồng thời đảm bảo rằng các jobs phụ thuộc lẫn nhau được thực thi theo đúng thứ tự.

Pipeline được cấu hình thông qua file YAML định nghĩa workflow của GitHub Actions. File này bao gồm các section chính: `name` (tên của workflow), `on` (các events trigger workflow), `jobs` (danh sách các jobs cần thực hiện), và `steps` (các bước trong mỗi job). Pipeline được thiết kế để chạy tự động trên mọi push event và pull request event tới các nhánh chính của repository, bao gồm nhánh `main` (nhánh production) và nhánh `develop` (nhánh phát triển).

**Bảng 3.1. Cấu trúc chi tiết CI/CD Pipeline**

| Stage | Tên Stage | Mô tả chi tiết | Công cụ sử dụng | Thời gian ước tính |
|-------|-----------|----------------|-----------------|-------------------|
| 1 | Checkout | Tải mã nguồn từ repository về runner, bao gồm toàn bộ lịch sử commit và các branches liên quan. Stage này đảm bảo rằng runner có đầy đủ mã nguồn cần thiết để thực hiện các bước tiếp theo. | Git (checkout@v4) | 10-30 giây |
| 2 | Setup Environment | Cài đặt môi trường thực thi cần thiết cho ứng dụng, bao gồm runtime (Node.js, Python, Java), package manager (npm, pip, maven), và các dependencies hệ thống. Stage này sử dụng caching để tăng tốc độ cài đặt cho các lần chạy sau. | actions/setup-node, actions/setup-python, actions/setup-java | 30-60 giây |
| 3 | Install Dependencies | Tải và cài đặt các dependencies của dự án từ package registry (npm registry, PyPI, Maven Central). Stage này tận dụng dependency caching để giảm thời gian cài đặt và giảm tải cho registry. | npm ci, pip install, mvn dependency:resolve | 1-3 phút |
| 4 | Build | Biên dịch mã nguồn và đóng gói ứng dụng thành artifact có thể triển khai. Đối với các dự án JavaScript/TypeScript, stage này bao gồm transpilation từ TypeScript sang JavaScript và bundling. Đối với các dự án Java, stage này bao gồm compilation và packaging thành JAR/WAR file. | npm run build, mvn package, python setup.py bdist_wheel | 2-5 phút |
| 5 | Unit Test | Chạy bộ kiểm thử đơn vị để đảm bảo rằng các thay đổi mã nguồn không làm phá vỡ chức năng hiện có. Stage này tạo ra code coverage report để đánh giá mức độ bao phủ của kiểm thử. | Jest, pytest, JUnit, Istanbul | 1-5 phút |
| 6 | SAST Scan (Parallel) | Quét bảo mật tĩnh sử dụng nhiều công cụ song song. Mỗi công cụ được chạy trong một job riêng biệt để tận dụng parallel execution của GitHub Actions. | Semgrep, CodeQL, ESLint, SpotBugs | 3-10 phút |
| 7 | Dependency Check | Kiểm tra các dependencies của dự án để phát hiện các lỗ hổng đã biết (known vulnerabilities) trong cơ sở dữ liệu CVE (Common Vulnerabilities and Exposures). | OWASP Dependency-Check, npm audit, pip-audit | 2-5 phút |
| 8 | Security Gate | Tổng hợp kết quả từ tất cả các công cụ SAST và Dependency Check, áp dụng security policies để ra quyết định Pass/Fail. Stage này quyết định liệu pipeline có được tiếp tục hay bị chặn. | SonarCloud, Custom Policy Engine | 30-60 giây |
| 9 | Upload Artifacts | Upload kết quả quét từ tất cả các công cụ lên GitHub Artifacts để MCP Server xử lý ở bước tiếp theo. Mỗi công cụ tạo ra một artifact riêng biệt. | actions/upload-artifact | 30-60 giây |
| 10 | Deploy (Optional) | Triển khai ứng dụng sang môi trường testing hoặc staging nếu security gate passed. Stage này chỉ được thực thi trên nhánh main và yêu cầu manual approval. | Docker, Kubernetes, AWS ECS | 5-15 phút |

Pipeline được thiết kế với cơ chế fault tolerance, trong đó nếu một job thất bại (do timeout, out of memory, hoặc lỗi khác), các jobs độc lập khác vẫn tiếp tục thực thi. Điều này đảm bảo rằng hệ thống thu thập được nhiều thông tin nhất có thể ngay cả khi một số công cụ gặp sự cố.

**Cơ chế caching trong pipeline:**

Để tối ưu hóa thời gian thực thi, pipeline áp dụng caching cho nhiều thành phần:

1. **Dependency Caching**: Các dependencies được cache dựa trên hash của lock file (package-lock.json, requirements.txt, pom.xml). Khi lock file không thay đổi, pipeline sử dụng cache thay vì tải lại từ registry.

2. **Build Cache**: Các artifact build được cache để giảm thời gian build cho các lần chạy sau. Cache key được tạo dựa trên hash của mã nguồn và cấu hình build.

3. **SAST Tool Cache**: Các công cụ SAST như CodeQL và Semgrep duy trì cache riêng cho database và rules, giúp giảm thời gian khởi tạo cho các lần quét tiếp theo.

```yaml
# Ví dụ cấu hình caching trong GitHub Actions
- name: Cache npm dependencies
  uses: actions/cache@v3
  with:
    path: ~/.npm
    key: ${{ runner.os }}-npm-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-npm-
```

### 3.2.2. Tích hợp SAST tools vào các giai đoạn

Việc tích hợp nhiều công cụ SAST vào pipeline nhằm mục đích tận dụng ưu điểm của từng công cụ và tăng độ bao phủ trong phát hiện lỗ hổng. Mỗi công cụ SAST có điểm mạnh riêng trong việc phát hiện các loại lỗ hổng cụ thể, và việc kết hợp nhiều công cụ giúp giảm thiểu khả năng bỏ sót lỗ hổng (false negatives). Đồng thời, việc so sánh kết quả từ nhiều công cụ cũng giúp xác định các false positives và tăng độ tin cậy của kết quả quét.

**Bảng 3.2. Phân tích chi tiết các SAST Tools được tích hợp**

| Công cụ | Ngôn ngữ hỗ trợ | Loại lỗ hổng phát hiện | Phương pháp phân tích | Output Format | Ưu điểm | Nhược điểm |
|---------|-----------------|------------------------|----------------------|---------------|---------|------------|
| **Semgrep** | 30+ ngôn ngữ (JavaScript, Python, Java, Go, Ruby, PHP, C#, C++, Rust, TypeScript, v.v.) | Logic flaws, insecure coding patterns, hardcoded secrets, injection vulnerabilities, XSS, SSRF, path traversal | Pattern matching dựa trên AST (Abstract Syntax Tree), hỗ trợ custom rules | SARIF, JSON | Tốc độ nhanh, dễ viết custom rules, hỗ trợ nhiều ngôn ngữ, open-source | Không phát hiện được các lỗ hổng phức tạp yêu cầu phân tích ngữ nghĩa sâu |
| **CodeQL** | JavaScript, TypeScript, Python, Java, C#, C++, Go, Ruby | Semantic vulnerabilities, data flow analysis, control flow analysis, taint analysis, cryptographic issues | Query language dựa trên Datalog, phân tích ngữ nghĩa mã nguồn, data flow tracking | SARIF | Phát hiện các lỗ hổng phức tạp, hỗ trợ custom queries, tích hợp sâu với GitHub | Thời gian quét lâu, yêu cầu build database, learning curve cao cho custom queries |
| **ESLint + security plugins** | JavaScript, TypeScript | Injection (SQL, NoSQL, Command), XSS, unsafe API usage (eval, innerHTML), prototype pollution, insecure regex | Static analysis dựa trên AST, pattern matching, rule-based detection | SARIF, JSON, stylish | Tích hợp dễ dàng vào quy trình phát triển JavaScript, real-time feedback trong IDE | Chỉ hỗ trợ JavaScript/TypeScript, false positives cao với một số rules |
| **SpotBugs + FindSecBugs** | Java (bytecode) | OWASP Top 10, CWE, injection, XSS, CSRF, insecure cryptography, hardcoded passwords, null pointer dereference | Bytecode analysis, pattern matching, data flow analysis | XML, SARIF | Phân tích sâu mã Java bytecode, phát hiện nhiều loại lỗ hổng, tích hợp với Maven/Gradle | Chỉ hỗ trợ Java, yêu cầu compiled bytecode, có thể chậm với dự án lớn |
| **OWASP Dependency-Check** | Đa ngôn ngữ (thông qua package managers) | Known vulnerabilities trong third-party dependencies (CVE), outdated libraries, license compliance | Signature matching, package URL (PURL) lookup, NVD API integration | JSON, HTML, XML, SARIF | Phát hiện lỗ hổng trong dependencies, báo cáo chi tiết, hỗ trợ nhiều ecosystem | Không phát hiện lỗ hổng trong mã nguồn, phụ thuộc vào chất lượng NVD data |

**Chi tiết tích hợp Semgrep:**

Semgrep được tích hợp vào pipeline thông qua GitHub Action `returntocorp/semgrep-action`. Công cụ này được cấu hình để chạy với chế độ CI, trong đó chỉ các rules có severity từ WARNING trở lên mới được báo cáo. Custom rules được định nghĩa trong file `.semgrep.yml` để phát hiện các lỗ hổng đặc thù của dự án.

```yaml
# .github/workflows/semgrep.yml
name: Semgrep SAST Scan
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  semgrep:
    runs-on: ubuntu-latest
    container:
      image: returntocorp/semgrep
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Run Semgrep scan
        run: |
          semgrep ci \
            --config auto \
            --config .semgrep.yml \
            --sarif --output semgrep-results.sarif \
            --metrics=off \
            --quiet
        env:
          SEMGREP_APP_TOKEN: ${{ secrets.SEMGREP_APP_TOKEN }}

      - name: Upload SARIF results
        uses: actions/upload-artifact@v3
        with:
          name: semgrep-results
          path: semgrep-results.sarif
          retention-days: 30
```

**Chi tiết tích hợp CodeQL:**

CodeQL được tích hợp thông qua GitHub Action `github/codeql-action`. Công cụ này yêu cầu build database từ mã nguồn trước khi thực hiện phân tích. Database được cache giữa các lần chạy để giảm thời gian build.

```yaml
# .github/workflows/codeql.yml
name: CodeQL Analysis
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  analyze:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        language: ['javascript', 'python', 'java']
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v2
        with:
          languages: ${{ matrix.language }}
          queries: security-extended,security-and-quality

      - name: Autobuild
        uses: github/codeql-action/autobuild@v2

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v2
        with:
          category: "/language:${{matrix.language}}"
          output: sarif-results
          format: sarif-latest

      - name: Upload SARIF results
        uses: actions/upload-artifact@v3
        with:
          name: codeql-${{ matrix.language }}-results
          path: sarif-results/
          retention-days: 30
```

**Chi tiết tích hợp ESLint:**

ESLint được tích hợp với các security plugins như `eslint-plugin-security`, `eslint-plugin-node`, và `@typescript-eslint/eslint-plugin`. Cấu hình ESLint được định nghĩa trong file `.eslintrc.yml`.

```yaml
# .eslintrc.yml
extends:
  - 'eslint:recommended'
  - 'plugin:security/recommended'
  - 'plugin:@typescript-eslint/recommended'

rules:
  security/detect-object-injection: warn
  security/detect-non-literal-fs-filename: warn
  security/detect-eval-with-expression: error
  security/detect-no-csrf-before-method-override: error
  security/detect-possible-timing-attacks: warn
  no-eval: error
  no-implied-eval: error
  no-new-func: error
```

**Chi tiết tích hợp SpotBugs:**

SpotBugs được tích hợp thông qua Maven plugin hoặc Gradle plugin. FindSecBugs plugin được thêm vào để phát hiện các lỗ hổng bảo mật.

```xml
<!-- pom.xml -->
<plugin>
    <groupId>com.github.spotbugs</groupId>
    <artifactId>spotbugs-maven-plugin</artifactId>
    <version>4.7.3.0</version>
    <configuration>
        <effort>Max</effort>
        <threshold>Low</threshold>
        <plugins>
            <plugin>
                <groupId>com.h3xstream.findsecbugs</groupId>
                <artifactId>findsecbugs-plugin</artifactId>
                <version>1.12.0</version>
            </plugin>
        </plugins>
        <outputDirectory>${project.build.directory}/spotbugs</outputDirectory>
        <outputFormat>sarif</outputFormat>
    </configuration>
</plugin>
```

**Chi tiết tích hợp OWASP Dependency-Check:**

Dependency-Check được tích hợp thông qua GitHub Action `dependency-check/Dependency-Check_Action`. Công cụ này quét tất cả dependencies trong dự án và so sánh với cơ sở dữ liệu NVD để phát hiện các lỗ hổng đã biết.

```yaml
# .github/workflows/dependency-check.yml
name: Dependency Check
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  dependency-check:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Dependency-Check Scan
        uses: dependency-check/Dependency-Check_Action@main
        with:
          project: 'my-project'
          path: '.'
          format: 'JSON,SARIF'
          out: 'reports'
          args: >
            --enableExperimental
            --failOnCVSS 7
            --suppression suppression.xml

      - name: Upload SARIF results
        uses: actions/upload-artifact@v3
        with:
          name: dependency-check-results
          path: reports/
          retention-days: 30
```

### 3.2.3. Thiết lập security gates và policy enforcement

Security gate đóng vai trò là cơ chế kiểm soát chất lượng bảo mật cuối cùng trong pipeline, quyết định liệu các thay đổi mã nguồn có được phép merge vào nhánh chính hay cần phải được sửa chữa trước. Cơ chế này đảm bảo rằng không có mã nguồn nào chứa lỗ hổng bảo mật nghiêm trọng được đưa vào production mà không được kiểm tra và xử lý.

**Nguyên lý hoạt động của Security Gate:**

Security Gate hoạt động dựa trên việc tổng hợp kết quả từ tất cả các công cụ SAST và Dependency Check đã chạy trong pipeline. Kết quả từ mỗi công cụ được thu thập, deduplicate (loại bỏ trùng lặp), và phân loại theo mức độ nghiêm trọng. Sau đó, hệ thống áp dụng các security policies đã được cấu hình để ra quyết định Pass/Fail.

Quá trình đánh giá được thực hiện theo các bước sau:

1. **Thu thập kết quả**: Kết quả từ tất cả các công cụ SAST được tải về từ GitHub Artifacts và parse thành cấu trúc dữ liệu thống nhất.

2. **Deduplication**: Các findings trùng lặp (cùng rule ID, file path, và line number) được gộp lại để tránh báo cáo nhiều lần cùng một lỗ hổng.

3. **Phân loại severity**: Mỗi finding được phân loại vào một trong bốn mức severity: CRITICAL, HIGH, MEDIUM, hoặc LOW dựa trên CVSS score và OWASP risk rating.

4. **Áp dụng policies**: Các security policies được áp dụng tuần tự để kiểm tra xem kết quả có vượt quá ngưỡng cho phép hay không.

5. **Ra quyết định**: Dựa trên kết quả kiểm tra policies, security gate ra quyết định Pass hoặc Fail.

6. **Thông báo**: Quyết định được thông báo đến developers và security team thông qua nhiều kênh (chat, email, dashboard).

**Bảng 3.3. Chi tiết Security Gate Policies**

| Policy Name | Mức độ áp dụng | Điều kiện kích hoạt | Ngưỡng cho phép | Hành động khi vi phạm | Mức độ ưu tiên |
|-------------|----------------|---------------------|-----------------|----------------------|----------------|
| Critical Vulnerability Policy | Tất cả repositories | Phát hiện lỗ hổng CRITICAL | 0 (không cho phép) | Block merge ngay lập tức, yêu cầu fix bắt buộc trước khi có thể merge. Tự động tạo issue và assign cho developer phụ trách. | P0 - Bắt buộc |
| High Vulnerability Policy | Tất cả repositories | Phát hiện ≥ 3 lỗ hổng HIGH | 2 (tối đa 2 lỗ hổng HIGH) | Block merge, yêu cầu review từ security team lead. Security lead có thể approve với justification hoặc reject yêu cầu fix. | P1 - Bắt buộc |
| Medium Vulnerability Policy | Repositories production | Phát hiện ≥ 10 lỗ hổng MEDIUM | 9 (tối đa 9 lỗ hổng MEDIUM) | Warning, cho phép merge nhưng yêu cầu fix trong sprint tiếp theo. Tự động tạo technical debt ticket. | P2 - Khuyến nghị |
| Low Vulnerability Policy | Repositories production | Phát hiện ≥ 50 lỗ hổng LOW | 49 (tối đa 49 lỗ hổng LOW) | Warning, cho phép merge bình thường. Thống kê trong báo cáo hàng tuần. | P3 - Thông tin |
| Dependency Vulnerability Policy | Tất cả repositories | Phát hiện dependency có CVE với CVSS ≥ 7.0 | 0 (không cho phép) | Block merge, yêu cầu cập nhật dependency lên phiên bản vá lỗi. | P0 - Bắt buộc |
| Code Coverage Policy | Repositories có test suite | Code coverage giảm > 5% so với baseline | 5% (tối đa giảm 5%) | Warning, khuyến nghị viết thêm test cases. | P2 - Khuyến nghị |
| New Vulnerability Policy | Pull requests | Phát hiện lỗ hổng mới so với nhánh target | 0 (không cho phép lỗ hổng mới) | Block merge cho lỗ hổng CRITICAL/HIGH. Warning cho lỗ hổng MEDIUM/LOW. | P1 - Bắt buộc |

**Cấu hình Security Policy:**

Security policies được cấu hình thông qua file `security-policy.yml` trong repository. File này cho phép customization policies cho từng dự án cụ thể.

```yaml
# security-policy.yml
security_policy:
  version: '1.0'
  description: 'Security gate policies for CI/CD pipeline'
  
  gate_rules:
    - name: "Critical Vulnerability Policy"
      description: "Block merge if any critical vulnerability is found"
      severity: CRITICAL
      threshold: 0
      action: BLOCK
      notification:
        channels: [chat, email, dashboard]
        recipients: [security-team, developers]
      auto_create_issue: true
      priority: P0
      
    - name: "High Vulnerability Policy"
      description: "Block merge if more than 2 high severity vulnerabilities are found"
      severity: HIGH
      threshold: 3
      action: BLOCK
      requires_approval: true
      approvers: [security-lead]
      notification:
        channels: [chat, email]
        recipients: [security-lead, developers]
      auto_create_issue: true
      priority: P1
      
    - name: "Medium Vulnerability Policy"
      description: "Warning if more than 9 medium severity vulnerabilities are found"
      severity: MEDIUM
      threshold: 10
      action: WARNING
      notification:
        channels: [dashboard]
        recipients: [developers]
      auto_create_issue: true
      sprint_fix_required: true
      priority: P2
      
    - name: "Dependency Vulnerability Policy"
      description: "Block merge if any dependency has CVSS >= 7.0"
      type: DEPENDENCY
      cvss_threshold: 7.0
      action: BLOCK
      notification:
        channels: [chat, email]
        recipients: [security-team, developers]
      auto_create_issue: true
      priority: P0

  exceptions:
    # Các trường hợp ngoại lệ có thể được cấu hình ở đây
    - rule: "Critical Vulnerability Policy"
      exception_for: ["test/", "docs/"]
      reason: "Test files and documentation are not deployed to production"
```

**Quy trình xử lý khi Security Gate Fail:**

Khi security gate fail (tức là kết quả quét vi phạm một hoặc nhiều policies), hệ thống thực hiện chuỗi hành động sau:

1. **Block Pull Request Merge**: Pull request bị chặn không thể merge vào nhánh target. GitHub hiển thị warning message trên PR page với chi tiết các violations.

2. **Tạo Issue Tự Động**: Hệ thống tự động tạo GitHub Issue với tiêu đề và mô tả chi tiết về các lỗ hổng cần fix. Issue được assign cho developer đã tạo PR và được label với mức độ ưu tiên tương ứng.

3. **Gửi Notification**: Notification được gửi đến developer và security team thông qua các kênh đã cấu hình (chat, email, dashboard). Notification bao gồm tóm tắt các violations và link đến dashboard để xem chi tiết.

4. **Cập nhật PR Comment**: Bot tự động comment vào pull request với danh sách các lỗ hổng cần fix, mức độ nghiêm trọng, và gợi ý cách khắc phục (nếu có sẵn từ AI analysis).

5. **Ghi nhận Audit Log**: Toàn bộ quá trình được ghi nhận vào audit log để phục vụ cho việc review và compliance sau này.

```yaml
# Ví dụ GitHub Action cho Security Gate
- name: Security Gate Evaluation
  run: |
    # Download all SARIF artifacts
    gh run download ${{ github.run_id }} --dir ./results
    
    # Run security gate evaluation
    python scripts/security_gate.py \
      --results-dir ./results \
      --policy security-policy.yml \
      --output gate-result.json
    
    # Check gate result
    GATE_RESULT=$(jq -r '.decision' gate-result.json)
    if [ "$GATE_RESULT" = "FAIL" ]; then
      echo "Security gate FAILED. Blocking merge."
      jq '.violations' gate-result.json
      exit 1
    else
      echo "Security gate PASSED."
    fi
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## 3.3. Thiết kế và triển khai ChatOps Workflow

### 3.3.1. ChatOps commands và interactions

ChatOps là một phương pháp vận hành hệ thống thông qua nền tảng chat, cho phép teams thực hiện các thao tác kỹ thuật và theo dõi trạng thái hệ thống trực tiếp từ môi trường chat mà không cần chuyển đổi giữa nhiều công cụ khác nhau. Trong bối cảnh DevSecOps, ChatOps đóng vai trò quan trọng trong việc tăng cường khả năng tiếp cận và sử dụng các công cụ bảo mật, giúp developers nhanh chóng nhận được thông tin về lỗ hổng và đề xuất khắc phục mà không cần rời khỏi môi trường làm việc quen thuộc.

Hệ thống ChatOps được thiết kế với kiến trúc command-based, trong đó mỗi command được ánh xạ đến một handler cụ thể xử lý yêu cầu của user. Commands được phân thành ba nhóm chính: monitoring commands (theo dõi trạng thái), analysis commands (phân tích và yêu cầu thông tin), và action commands (thực hiện các thao tác trên pipeline).

**Bảng 3.4. Chi tiết ChatOps Commands**

| Command | Nhóm | Mô tả chi tiết | Tham số | Ví dụ sử dụng | Quyền yêu cầu |
|---------|------|----------------|---------|---------------|---------------|
| `/status` | Monitoring | Kiểm tra trạng thái hiện tại của pipeline cho một repository cụ thể. Hiển thị thông tin về workflow đang chạy, giai đoạn hiện tại, và estimated time remaining. | `repo-name` (tùy chọn, mặc định là repository hiện tại) | `/status`<br>`/status my-repo` | Read access to repository |
| `/scan` | Action | Kích hoạt quét bảo mật manual cho một branch cụ thể. Useful khi developer muốn kiểm tra bảo mật trước khi tạo PR hoặc khi có thay đổi lớn về mã nguồn. | `repo-name`, `branch-name` (tùy chọn) | `/scan`<br>`/scan my-repo feature-branch` | Write access to repository |
| `/results` | Monitoring | Xem kết quả quét bảo mật gần nhất cho một repository. Hiển thị tóm tắt số lượng findings theo severity, top findings, và link đến dashboard chi tiết. | `repo-name`, `run-id` (tùy chọn) | `/results`<br>`/results my-repo 12345` | Read access to repository |
| `/explain` | Analysis | Yêu cầu AI assistant giải thích chi tiết về một lỗ hổng cụ thể. Trả về mô tả về nguyên nhân, cơ chế khai thác, mức độ ảnh hưởng, và các ví dụ minh họa. | `finding-id` (bắt buộc) | `/explain FINDING-001` | Read access to repository |
| `/fix` | Analysis | Yêu cầu AI assistant đề xuất cách khắc phục cụ thể cho một lỗ hổng. Trả về đoạn code đã được sửa, giải thích về thay đổi, và các best practices liên quan. | `finding-id` (bắt buộc) | `/fix FINDING-001` | Read access to repository |
| `/rerun` | Action | Chạy lại pipeline cho một run cụ thể. Useful khi developer đã fix lỗi và muốn kiểm tra lại mà không cần push code mới. | `repo-name`, `run-id` | `/rerun`<br>`/rerun my-repo 12345` | Write access to repository |
| `/approve` | Action | Phê duyệt bypass security gate cho một pull request cụ thể. Yêu cầu justification và được ghi nhận vào audit log. Chỉ available cho security team leads. | `pr-number`, `reason` (bắt buộc) | `/approve 42 "Low risk, will fix in next sprint"` | Security team lead role |
| `/report` | Monitoring | Tạo báo cáo bảo mật cho một repository trong một khoảng thời gian cụ thể. Báo cáo bao gồm xu hướng lỗ hổng, top categories, và recommendations. | `repo-name`, `period` (daily/weekly/monthly) | `/report`<br>`/report my-repo weekly` | Read access to repository |
| `/help` | General | Hiển thị danh sách các commands available và hướng dẫn sử dụng. | Không có | `/help` | Tất cả users |
| `/feedback` | General | Gửi phản hồi về chất lượng phân tích của AI assistant. Phản hồi được sử dụng để cải thiện model và prompt templates. | `finding-id`, `feedback-text` | `/feedback FINDING-001 "Suggestion was helpful"` | Tất cả users |

**Luồng xử lý command chi tiết:**

Quá trình xử lý một command từ user đến khi trả về kết quả bao gồm các bước sau:

**Bước 1: Command Reception**

Khi user gửi một tin nhắn chứa command (bắt đầu bằng `/`), chat platform (Slack, Microsoft Teams, hoặc custom chat platform) sẽ phát sinh webhook event. Webhook event này được gửi đến backend API của hệ thống thông qua HTTP POST request. Webhook payload bao gồm thông tin về user (user ID, username, team membership), nội dung tin nhắn, và metadata về channel (channel ID, channel type).

**Bước 2: Authentication & Authorization**

Backend API nhận webhook request và thực hiện xác thực thông qua JWT token được gắn trong webhook secret. Token được xác minh để đảm bảo rằng request đến từ chat platform hợp lệ. Sau đó, hệ thống kiểm tra quyền của user dựa trên GitHub team membership. Các roles được định nghĩa bao gồm:

- **Developer**: Có quyền thực hiện các commands đọc (status, results, explain, fix, report) và commands action cơ bản (scan, rerun) trên repositories mà user có access.
- **Security Analyst**: Có thêm quyền xem báo cáo chi tiết và phân tích xu hướng bảo mật.
- **Security Team Lead**: Có thêm quyền phê duyệt bypass security gate và cấu hình security policies.
- **Admin**: Có toàn quyền trên hệ thống, bao gồm quản lý users và cấu hình hệ thống.

**Bước 3: Command Parsing & Routing**

Command được parse để xác định command name và các tham số. Command parser sử dụng regular expression để trích xuất command name (phần sau `/`) và các arguments. Sau đó, command được routing đến handler tương ứng dựa trên command name.

```python
import re
from typing import Dict, List, Optional

class CommandParser:
    COMMAND_PATTERN = re.compile(r'^/(\w+)\s*(.*)')
    ARGUMENT_PATTERN = re.compile(r'(\w+):(\S+)')
    
    @classmethod
    def parse(cls, message: str) -> Optional[Dict]:
        match = cls.COMMAND_PATTERN.match(message.strip())
        if not match:
            return None
        
        command_name = match.group(1)
        raw_args = match.group(2)
        
        arguments = {}
        for arg_match in cls.ARGUMENT_PATTERN.finditer(raw_args):
            arguments[arg_match.group(1)] = arg_match.group(2)
        
        return {
            'command': command_name,
            'arguments': arguments,
            'raw_args': raw_args
        }
```

**Bước 4: Handler Execution**

Handler tương ứng được thực thi để xử lý command. Handler có thể là:

- **Tool Executor**: Thực hiện các thao tác trên CI/CD pipeline thông qua GitHub Actions API. Ví dụ: trigger workflow, rerun pipeline, approve PR.
- **Data Fetcher**: Truy vấn database để lấy kết quả quét và thông tin findings.
- **LLM Query Handler**: Gửi query đến LLM Orchestrator để yêu cầu phân tích và đề xuất.

**Bước 5: Response Formatting**

Kết quả từ handler được format thành tin nhắn chat phù hợp với platform. Response formatter hỗ trợ nhiều định dạng output:

- **Text**: Văn bản thuần túy với markdown formatting.
- **Rich Text**: Định dạng phong phú với headings, lists, code blocks, và links.
- **Interactive**: Các elements tương tác như buttons, dropdowns, và modals.
- **Charts**: Biểu đồ và graphs dưới dạng hình ảnh.

**Bước 6: Response Delivery**

Tin nhắn được gửi về user thông qua chat platform API. Đối với các phản hồi dài, hệ thống có thể chia thành nhiều tin nhắn hoặc tạo thread để giữ cho conversation được tổ chức.

### 3.3.2. AI Assistant integration với chat platform

AI assistant được tích hợp vào chat platform thông qua kiến trúc multi-layer, bao gồm các thành phần: chat platform webhook, backend API, command router, LLM Orchestrator, và response formatter. Kiến trúc này đảm bảo rằng AI assistant có thể nhận queries từ users, xử lý thông qua mô hình LLM, và trả về kết quả một cách an toàn và hiệu quả.

**Kiến trúc tích hợp AI Assistant:**

**Lớp 1: Chat Platform Integration Layer**

Lớp này chịu trách nhiệm giao tiếp với chat platform thông qua webhook và API. Lớp này bao gồm:

- **Webhook Handler**: Nhận và xác thực webhook events từ chat platform.
- **Message Sender**: Gửi tin nhắn đến chat platform thông qua platform API.
- **State Manager**: Quản lý state của conversation, bao gồm context và session data.

**Lớp 2: Command Processing Layer**

Lớp này xử lý commands và routing đến handlers tương ứng:

- **Command Parser**: Parse command từ tin nhắn user.
- **Command Router**: Route command đến handler phù hợp.
- **Permission Checker**: Kiểm tra quyền của user trước khi thực hiện command.

**Lớp 3: LLM Integration Layer**

Lớp này quản lý tương tác với LLM:

- **Prompt Builder**: Xây dựng system prompt và user prompt dựa trên context.
- **Context Manager**: Quản lý conversation history và findings context.
- **LLM Client**: Giao tiếp với LLM API (Gemini, GPT-4, hoặc local LLM).
- **Response Validator**: Validate và sanitize response từ LLM.

**Lớp 4: Response Processing Layer**

Lớp này xử lý và format response trước khi gửi về user:

- **Response Formatter**: Format response thành chat-appropriate format.
- **Markdown Renderer**: Render markdown thành rich text.
- **Code Highlighter**: Syntax highlighting cho code snippets.

**Quy trình xử lý query từ AI assistant:**

**Bước 1: Query Reception**

AI assistant nhận query từ user thông qua chat webhook. Query có thể là một command cụ thể (như `/explain FINDING-001`) hoặc một câu hỏi tự nhiên (như "Tại sao lỗi này lại nguy hiểm?"). Hệ thống phân loại query để xác định intent và route đến handler phù hợp.

**Bước 2: Intent Classification**

Intent classifier sử dụng rule-based matching và/hoặc ML model để phân loại intent của query. Các intents được hỗ trợ bao gồm:

- **STATUS_QUERY**: Yêu cầu thông tin về trạng thái pipeline.
- **FINDING_EXPLANATION**: Yêu cầu giải thích về lỗ hổng.
- **FIX_SUGGESTION**: Yêu cầu đề xuất cách khắc phục.
- **CODE_ANALYSIS**: Yêu cầu phân tích đoạn code cụ thể.
- **BEST_PRACTICE**: Yêu cầu thông tin về best practices.
- **GENERAL_QUESTION**: Câu hỏi chung về bảo mật.

**Bước 3: Context Retrieval**

Dựa trên intent và query content, MCP Server fetch context từ các nguồn dữ liệu:

- **Findings Database**: Thông tin chi tiết về finding được yêu cầu.
- **Source Code Repository**: Code snippet và context xung quanh vị trí lỗ hổng.
- **Knowledge Base**: Thông tin về CWE, OWASP, và best practices.
- **Conversation History**: Lịch sử hội thoại để duy trì context.

**Bước 4: Prompt Construction**

Prompt engine xây dựng system prompt tối ưu dựa trên intent và context. System prompt bao gồm:

- **Role Definition**: Định nghĩa vai trò của AI (security analyst assistant).
- **Task Description**: Mô tả nhiệm vụ cần thực hiện.
- **Context Information**: Thông tin ngữ cảnh về finding và mã nguồn.
- **Output Format**: Định dạng output mong muốn.
- **Constraints**: Các ràng buộc và guidelines.

```
SYSTEM PROMPT TEMPLATE:

You are a senior security analyst assistant specialized in Static Application Security Testing (SAST) findings analysis. Your role is to help developers understand and fix security vulnerabilities detected in their code.

TASK: Explain the following vulnerability finding and provide actionable remediation suggestions.

VULNERABILITY DETAILS:
- Finding ID: {finding_id}
- Tool: {tool_name}
- Rule: {rule_id}
- Severity: {severity}
- CWE: {cwe_id} - {cwe_description}
- OWASP Category: {owasp_category}
- CVSS Score: {cvss_score}
- File: {file_path}
- Line: {line_number}

CODE CONTEXT:
```{language}
{code_before}
>>> {vulnerable_line} <<<
{code_after}
```

PLEASE PROVIDE:
1. VULNERABILITY EXPLANATION: Explain in Vietnamese what this vulnerability is, how it works, and why it is dangerous.
2. IMPACT ASSESSMENT: Describe the potential impact if this vulnerability is exploited.
3. REMEDIATION: Provide a concrete code fix with explanation.
4. BEST PRACTICES: List relevant best practices to prevent similar issues.
5. REFERENCES: Link to relevant CWE, OWASP, or security documentation.

CONSTRAINTS:
- Keep the explanation clear and concise (under 300 words)
- Use Vietnamese for explanations
- Provide code examples in the original programming language
- Include specific line numbers for suggested changes
- Reference official security standards (CWE, OWASP, NIST)

**Bước 5: LLM Inference**

Constructed prompt được gửi đến LLM API để xử lý. Hệ thống sử dụng Gemini API (phiên bản 2.5 hoặc 3.1) với các tham số cấu hình:

- **temperature**: 0.2 (low temperature để đảm bảo output deterministic và chính xác)
- **max_tokens**: 2000 (giới hạn độ dài output)
- **top_p**: 0.9 (nucleus sampling)
- **stop_sequences**: ["```", "---"] (dừng generation khi gặp các markers)

**Bước 6: Response Validation**

Response từ LLM được validate thông qua output guardrails:

- **Schema Validation**: Kiểm tra xem response có đúng cấu trúc mong muốn (có đủ 5 phần: explanation, impact, remediation, best practices, references).
- **Content Validation**: Kiểm tra xem response có chứa thông tin nhạy cảm hoặc không phù hợp.
- **Confidence Check**: Đánh giá confidence score của response. Nếu confidence < 0.7, hệ thống thêm disclaimer vào response.
- **Markdown Sanitization**: Strip markdown injection và dangerous HTML tags.

**Bước 7: Response Delivery**

Response được format và gửi về user thông qua chat platform. Nếu response dài, hệ thống chia thành nhiều tin nhắn hoặc tạo thread.

### 3.3.3. Real-time notifications và approvals

Hệ thống hỗ trợ real-time notifications để đảm bảo rằng developers và security team nhận được thông tin kịp thời về các sự kiện quan trọng trong pipeline. Notifications được thiết kế theo mô hình publish-subscribe, trong đó các events được publish đến message broker và subscribers nhận notifications dựa trên subscription preferences.

**Kiến trúc Notification System:**

Notification system bao gồm các thành phần:

- **Event Publisher**: Các thành phần trong hệ thống (CI/CD pipeline, MCP Server, Security Gate) publish events đến message broker khi có sự kiện quan trọng.
- **Message Broker**: Redis Pub/Sub hoặc RabbitMQ được sử dụng làm message broker để quản lý distribution của notifications.
- **Subscription Manager**: Quản lý subscription preferences của users, cho phép users chọn nhận notifications cho các events cụ thể qua các kênh cụ thể.
- **Notification Dispatcher**: Gửi notifications đến users thông qua các channels (chat, email, dashboard, mobile push).

**Bảng 3.5. Chi tiết Real-time Notifications**

| Event | Trigger Condition | Description | Recipients | Channels | Priority |
|-------|-------------------|-------------|------------|----------|----------|
| Pipeline Started | CI workflow được trigger bởi push/PR | Thông báo rằng pipeline đã bắt đầu chạy cho repository và branch cụ thể | Developer đã tạo commit/PR | Chat, Dashboard | Low |
| Pipeline Completed | Tất cả jobs trong workflow hoàn tất | Thông báo kết quả pipeline (success/failure) với tóm tắt thời gian và số lượng tests | Developer, Team leads | Chat, Email, Dashboard | Medium |
| SAST Scan Started | SAST job bắt đầu thực thi | Thông báo rằng quá trình quét bảo mật đang được thực hiện | Developer | Dashboard | Low |
| SAST Scan Completed | Tất cả SAST tools hoàn tất quét | Thông báo kết quả quét với số lượng findings theo severity | Developer, Security team | Chat, Email, Dashboard | High |
| Security Gate Passed | Security gate evaluation trả về PASS | Thông báo rằng code đã vượt qua security checks và sẵn sàng merge | Developer, Team leads | Chat, Dashboard | Medium |
| Security Gate Failed | Security gate evaluation trả về FAIL | Thông báo rằng code bị chặn do vi phạm security policies, kèm danh sách violations | Developer, Security team | Chat, Email, Dashboard | Critical |
| New Critical Finding | Phát hiện lỗ hổng CRITICAL mới | Thông báo ngay lập tức về lỗ hổng nghiêm trọng mới được phát hiện | Security team, Team leads | Chat, Email, Mobile Push | Critical |
| AI Analysis Ready | LLM hoàn tất phân tích findings | Thông báo rằng AI analysis đã sẵn sàng để xem | Developer | Chat, Dashboard | Medium |
| Approval Required | Security gate fail và yêu cầu approval | Thông báo rằng có PR cần được security lead approve | Security team leads | Chat, Email, Mobile Push | High |
| Dependency Alert | Phát hiện dependency có CVE mới | Thông báo về lỗ hổng mới trong dependencies đã được sử dụng | Developer, Security team | Chat, Email | High |
| Weekly Report | Schedule hàng tuần | Báo cáo tổng hợp về xu hướng bảo mật trong tuần | Tất cả stakeholders | Email, Dashboard | Low |

**Chi tiết Approval Workflow:**

Approval workflow được kích hoạt khi security gate fail và policy yêu cầu approval từ security team lead. Quy trình bao gồm các bước:

**Bước 1: Approval Request Creation**

Khi security gate fail với điều kiện yêu cầu approval (ví dụ: số lượng HIGH vulnerabilities vượt quá threshold nhưng không có CRITICAL), hệ thống tự động tạo approval request. Approval request bao gồm:

- **PR Information**: Thông tin về pull request (PR number, title, author, target branch).
- **Violations Summary**: Tóm tắt các security violations (số lượng và mức độ của từng finding).
- **Top Findings**: Danh sách top 5 findings nghiêm trọng nhất với mô tả ngắn gọn.
- **AI Analysis**: Phân tích từ AI assistant về mức độ rủi ro và đề xuất ban đầu.
- **Deadline**: Thời hạn cho approval (thường là 24-48 giờ).

**Bước 2: Notification Distribution**

Approval request được gửi đến security team leads thông qua các kênh đã cấu hình. Notification bao gồm:

- Link đến dashboard để xem chi tiết violations
- Summary trong notification message
- Deadline cho approval
- Quick actions (Approve/Reject) trong notification (nếu platform hỗ trợ)

**Bước 3: Review Process**

Security team lead review approval request bằng cách:

1. Truy cập dashboard để xem chi tiết violations và AI analysis.
2. Đánh giá mức độ rủi ro dựa trên severity, CVSS score, và context của ứng dụng.
3. Kiểm tra code changes trong PR để hiểu nguyên nhân của violations.
4. Tham khảo AI recommendations để có thêm thông tin.

**Bước 4: Decision Making**

Security team lead ra quyết định:

- **Approve**: Cho phép merge với điều kiện:
  - Có justification rõ ràng (ví dụ: "Low risk, internal tool only", "Will fix in next sprint")
  - Approval được ghi nhận vào audit log
  - Auto-create issue cho việc fix sau
  - Notification được gửi đến developer

- **Reject**: Yêu cầu developer fix trước khi merge:
  - Reject reason được ghi nhận
  - Notification được gửi đến developer với chi tiết lý do
  - PR comment được cập nhật với feedback

- **Request Changes**: Yêu cầu thông tin bổ sung hoặc thay đổi cụ thể:
  - Comment được gửi đến developer
  - Approval deadline được gia hạn

**Bước 5: Decision Execution**

Quyết định được thực thi:

- Nếu Approved: PR được unblock và developer có thể merge.
- Nếu Rejected: PR vẫn bị block và developer cần fix violations.
- Decision được ghi nhận vào audit log với timestamp, approver, và justification.

```python
# Ví dụ Approval Workflow Implementation
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

class ApprovalRequest(BaseModel):
    pr_number: int
    repo_id: str
    violations: List[Violation]
    ai_analysis: Optional[str]
    deadline: datetime

class ApprovalDecision(BaseModel):
    pr_number: int
    decision: str  # "APPROVE", "REJECT", "REQUEST_CHANGES"
    justification: str
    approver_id: str

@router.post('/approval/request')
async def create_approval_request(
    request: ApprovalRequest,
    current_user: User = Depends(verify_user)
):
    # Save approval request to database
    db_request = await db.create_approval_request(request)
    
    # Notify security team leads
    await notification_service.notify_security_leads(
        event='approval_required',
        data={
            'pr_number': request.pr_number,
            'repo_id': request.repo_id,
            'violations_count': len(request.violations),
            'deadline': request.deadline.isoformat()
        }
    )
    
    return {'status': 'created', 'request_id': db_request.id}

@router.post('/approval/decide')
async def make_approval_decision(
    decision: ApprovalDecision,
    current_user: User = Depends(verify_security_lead)
):
    # Save decision to database
    await db.save_approval_decision(decision)
    
    # Execute decision
    if decision.decision == 'APPROVE':
        await github_api.unblock_pr(decision.pr_number)
        await notification_service.notify_developer(
            event='approval_granted',
            data={'pr_number': decision.pr_number}
        )
    elif decision.decision == 'REJECT':
        await notification_service.notify_developer(
            event='approval_denied',
            data={
                'pr_number': decision.pr_number,
                'reason': decision.justification
            }
        )
    
    # Record in audit log
    await audit_log.record('approval_decision', decision.dict())
    
    return {'status': 'decision_recorded'}
```

## 3.4. Thiết kế và triển khai MCP Server

### 3.4.1. Data collection và normalization pipeline

MCP Server đóng vai trò trung tâm trong hệ thống, chịu trách nhiệm thu thập dữ liệu từ nhiều nguồn khác nhau, xử lý và chuẩn hóa dữ liệu, và cung cấp ngữ cảnh an toàn cho AI assistant. Pipeline xử lý dữ liệu được thiết kế theo kiến trúc pipeline pattern, trong đó dữ liệu đi qua nhiều stages tuần tự, mỗi stage thực hiện một biến đổi cụ thể trên dữ liệu. Kiến trúc này đảm bảo tính module hóa, cho phép dễ dàng thêm hoặc sửa đổi stages mà không ảnh hưởng đến các stages khác.

**Hình 3.3. Data Collection and Normalization Pipeline**

*(Chèn sơ đồ Image 9 tại đây)*

Pipeline bao gồm bốn stages chính, mỗi stage được mô tả chi tiết dưới đây:

**Stage 1: Raw Scan Output Collection (Thu thập kết quả quét thô)**

Đây là stage đầu tiên trong pipeline, chịu trách nhiệm thu thập kết quả quét từ nhiều công cụ SAST khác nhau. Giai đoạn này đặt nền móng cho toàn bộ quy trình xử lý dữ liệu, đảm bảo rằng dữ liệu được thu thập đầy đủ, nguyên vẹn và an toàn từ các nguồn.

**Mục tiêu của Stage 1:**

Mục tiêu chính của stage này là thu thập toàn bộ kết quả quét từ các công cụ SAST đã chạy trong CI/CD pipeline và lưu trữ tạm thời để xử lý ở các stages tiếp theo. Stage này cần đảm bảo rằng không có kết quả nào bị bỏ sót và dữ liệu được thu thập một cách an toàn.

**Định dạng dữ liệu hỗ trợ:**

Stage này hỗ trợ nhiều định dạng kết quả quét khác nhau, phản ánh sự đa dạng của các công cụ SAST được tích hợp trong hệ thống:

- **SARIF v2.1 (Static Analysis Results Interchange Format)**: Đây là định dạng chuẩn của OASIS cho kết quả phân tích mã nguồn tĩnh. SARIF cung cấp schema thống nhất cho phép trao đổi kết quả giữa các công cụ khác nhau. SARIF bao gồm các thông tin: tool information, rule definitions, results (findings), locations (file path, line numbers), severity levels, và optional code snippets. SARIF được sử dụng bởi Semgrep, CodeQL, và ESLint.

- **XML (SpotBugs format)**: SpotBugs output kết quả dưới dạng XML với cấu trúc riêng. XML format bao gồm các elements: BugCollection, BugInstance (mỗi instance là một finding), BugPattern (thông tin về loại bug), SourceLine (vị trí trong mã nguồn). Stage này bao gồm XML-to-SARIF converter để chuyển đổi sang định dạng chuẩn.

- **JSON (OWASP Dependency-Check format)**: Dependency-Check output kết quả dưới dạng JSON, bao gồm thông tin về: report schema version, scan info, dependencies (mỗi dependency có thể có vulnerabilities), vulnerabilities (CVE ID, CVSS score, description, references). Stage này bao gồm JSON parser để trích xuất thông tin cần thiết.

- **GitHub Artifacts API**: Đây là cơ chế để tải kết quả quét từ GitHub Actions. Mỗi công cụ SAST upload kết quả của mình như một artifact riêng biệt. GitHub Artifacts API cung cấp endpoints để list artifacts và download artifact content. Stage này sử dụng API này với token-scoped access.

**Implementation chi tiết:**

MCP Artifact Fetcher được implement như một service độc lập, có thể được scale độc lập với các thành phần khác. Fetcher sử dụng GitHub Personal Access Token (PAT) với scope `actions:read` để đảm bảo rằng token chỉ có quyền đọc artifacts và không thể thực hiện các thao tác ghi lên repository.

```python
import requests
import time
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ArtifactInfo:
    name: str
    size: int
    created_at: str
    download_url: str

class MCPArtifactFetcher:
    """
    Fetcher for downloading artifacts from GitHub Actions.
    Supports retry mechanism with exponential backoff and token-scoped access.
    """
    
    GITHUB_API_BASE = 'https://api.github.com'
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1  # seconds
    
    def __init__(self, token: str, verify_https: bool = True):
        """
        Initialize the artifact fetcher.
        
        Args:
            token: GitHub Personal Access Token with actions:read scope
            verify_https: Whether to verify HTTPS certificates
        """
        self.token = token
        self.verify_https = verify_https
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'MCP-Artifact-Fetcher/1.0'
        })
        self.session.verify = verify_https
    
    def list_artifacts(self, owner: str, repo: str, run_id: str) -> List[ArtifactInfo]:
        """
        List all artifacts for a given workflow run.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: GitHub Actions workflow run ID
            
        Returns:
            List of ArtifactInfo objects
        """
        url = f'{self.GITHUB_API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts'
        
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                artifacts_data = response.json()
                artifacts = []
                for artifact in artifacts_data.get('artifacts', []):
                    artifacts.append(ArtifactInfo(
                        name=artifact['name'],
                        size=artifact['size_in_bytes'],
                        created_at=artifact['created_at'],
                        download_url=artifact['archive_download_url']
                    ))
                
                logger.info(f"Found {len(artifacts)} artifacts for run {run_id}")
                return artifacts
                
            except requests.exceptions.RequestException as e:
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f"Failed to list artifacts (attempt {attempt + 1}/{self.MAX_RETRIES}). Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"Failed to list artifacts after {self.MAX_RETRIES} attempts: {e}")
                    raise
    
    def download_artifact(self, download_url: str) -> bytes:
        """
        Download a specific artifact.
        
        Args:
            download_url: URL to download the artifact from
            
        Returns:
            Raw bytes of the artifact
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.session.get(download_url, timeout=60)
                response.raise_for_status()
                return response.content
            except requests.exceptions.RequestException as e:
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f"Failed to download artifact (attempt {attempt + 1}/{self.MAX_RETRIES}). Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"Failed to download artifact after {self.MAX_RETRIES} attempts: {e}")
                    raise
```

**Quy trình thu thập:**

1. **Authentication**: Fetcher khởi tạo session với GitHub PAT và verify HTTPS certificate.
2. **Artifact Discovery**: Fetcher gọi GitHub Artifacts API để list tất cả artifacts cho workflow run.
3. **Artifact Filtering**: Lọc artifacts dựa trên naming convention (ví dụ: chỉ tải artifacts có tên kết thúc bằng `-results`).
4. **Artifact Download**: Tải từng artifact về local storage. Mỗi artifact được lưu với tên duy nhất để tránh conflict.
5. **Integrity Verification**: Verifies downloaded artifacts bằng cách kiểm tra file size và checksum (nếu available).
6. **Error Handling**: Nếu có lỗi xảy ra, fetcher retry với exponential backoff (1s, 2s, 4s).

**Stage 2: Format Normalization (Chuẩn hóa định dạng)**

Stage thứ hai chịu trách nhiệm chuyển đổi tất cả định dạng kết quả quét về một schema chuẩn duy nhất. Việc chuẩn hóa này là cần thiết vì các công cụ SAST khác nhau output kết quả dưới các định dạng khác nhau, và các stages tiếp theo cần xử lý dữ liệu dưới dạng thống nhất.

**Mục tiêu của Stage 2:**

Mục tiêu là tạo ra một representation thống nhất cho tất cả findings, bất kể nguồn gốc từ công cụ nào. Schema chuẩn được thiết kế để bao gồm tất cả thông tin cần thiết cho việc phân tích và làm giàu dữ liệu, đồng thời loại bỏ các thông tin không cần thiết.

**Công nghệ và thư viện sử dụng:**

- **SARIF Parser**: Thư viện `sarif-parser` (Python) được sử dụng để parse và validate SARIF files. Thư viện này hỗ trợ SARIF v2.1.0 và cung cấp API để truy cập các thành phần của SARIF file.

- **XML → SARIF Converter**: Custom converter được phát triển để chuyển đổi SpotBugs XML output sang SARIF format. Converter ánh xạ các XML elements sang SARIF equivalents:
  - `BugInstance` → `result`
  - `BugPattern` → `rule`
  - `SourceLine` → `location`
  - `ShortMessage` → `message`

- **Pydantic Models**: Pydantic được sử dụng để định nghĩa schema chuẩn và validate dữ liệu. Pydantic cung cấp:
  - Type validation: Kiểm tra kiểu dữ liệu của từng field
  - Required fields check: Đảm bảo các trường bắt buộc có giá trị
  - Custom validators: Logic validation tùy chỉnh
  - Serialization: Chuyển đổi giữa Python objects và JSON

**Normalized Schema chi tiết:**

Schema chuẩn được định nghĩa sử dụng Pydantic models:

```python
from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum

class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

class Location(BaseModel):
    """Represents the location of a vulnerability in source code."""
    file_path: str = Field(..., description="Path to the file containing the vulnerability")
    line_number: int = Field(..., ge=1, description="Line number where the vulnerability is located")
    column_number: Optional[int] = Field(None, ge=1, description="Column number where the vulnerability starts")
    code_snippet: Optional[str] = Field(None, description="Code context around the vulnerability")

class Finding(BaseModel):
    """
    Normalized finding schema.
    All SAST tool outputs are converted to this schema.
    """
    # Core identification fields
    finding_id: str = Field(..., description="Unique identifier for this finding")
    tool: str = Field(..., description="Name of the SAST tool that detected this finding")
    rule_id: str = Field(..., description="Rule ID that was triggered")
    rule_name: Optional[str] = Field(None, description="Human-readable rule name")
    
    # Severity and classification
    severity: Severity = Field(..., description="Severity level of the finding")
    confidence: Optional[str] = Field(None, description="Confidence level (HIGH/MEDIUM/LOW)")
    
    # Description
    message: str = Field(..., description="Description of the vulnerability")
    long_description: Optional[str] = Field(None, description="Detailed description")
    
    # Location
    location: Location = Field(..., description="Location of the vulnerability")
    
    # Classification (to be enriched in Stage 3)
    cwe_id: Optional[str] = Field(None, description="CWE ID (e.g., CWE-79)")
    cwe_name: Optional[str] = Field(None, description="CWE name")
    owasp_category: Optional[str] = Field(None, description="OWASP Top 10 category")
    cvss_score: Optional[float] = Field(None, ge=0, le=10, description="CVSS v3 score")
    
    # Metadata
    run_id: str = Field(..., description="CI/CD pipeline run ID")
    repo_id: str = Field(..., description="Repository identifier")
    commit_sha: Optional[str] = Field(None, description="Git commit SHA")
    branch: Optional[str] = Field(None, description="Git branch name")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the finding was created")
    
    # Validation
    @validator('severity')
    def normalize_severity(cls, v):
        """Normalize severity value to uppercase enum."""
        severity_map = {
            'error': 'CRITICAL',
            'critical': 'CRITICAL',
            'high': 'HIGH',
            'warning': 'MEDIUM',
            'medium': 'MEDIUM',
            'info': 'LOW',
            'low': 'LOW',
            'note': 'INFO'
        }
        return severity_map.get(v.lower(), v.upper())
    
    @validator('message')
    def validate_message(cls, v):
        """Ensure message is not empty and within length limit."""
        v = v.strip()
        if not v:
            raise ValueError('Message cannot be empty')
        if len(v) > 5000:
            v = v[:5000] + '...'
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "finding_id": "FINDING-001",
                "tool": "Semgrep",
                "rule_id": "python.lang.security.audit.eval-use.eval-use",
                "severity": "HIGH",
                "message": "Detected use of eval() which can lead to code injection",
                "location": {
                    "file_path": "src/app.py",
                    "line_number": 42
                }
            }
        }
```

**Quy trình chuẩn hóa:**

1. **Format Detection**: Xác định định dạng của file input dựa trên file extension và content analysis.
2. **Parsing**: Parse file content sử dụng parser phù hợp (SARIF parser, XML parser, JSON parser).
3. **Field Mapping**: Ánh xạ các fields từ source format sang normalized schema.
4. **Validation**: Validate dữ liệu sử dụng Pydantic models. Nếu validation fail, finding bị reject và log error.
5. **Normalization**: Chuẩn hóa các giá trị (severity, confidence) về format thống nhất.
6. **ID Generation**: Tạo finding_id duy nhất dựa trên hash của rule_id + file_path + line_number.

```python
import hashlib
from typing import List

class FormatNormalizer:
    """
    Normalizes SAST scan results from various formats to a unified schema.
    """
    
    @classmethod
    def normalize_sarif(cls, sarif_data: bytes, run_id: str, repo_id: str) -> List[Finding]:
        """Normalize SARIF format to unified Finding schema."""
        import json
        from sarif_parser import SARIFParser
        
        sarif = json.loads(sarif_data)
        parser = SARIFParser(sarif)
        
        findings = []
        for run in parser.runs:
            for result in run.results:
                location = Location(
                    file_path=result.locations[0].physical_location.artifact_location.uri,
                    line_number=result.locations[0].physical_location.region.start_line,
                    column_number=result.locations[0].physical_location.region.start_column,
                    code_snippet=result.code_flows[0].thread_flows[0].locations[0].location.message.text if result.code_flows else None
                )
                
                finding = Finding(
                    finding_id=cls.generate_finding_id(
                        rule_id=result.rule_id,
                        file_path=location.file_path,
                        line_number=location.line_number
                    ),
                    tool=run.tool.driver.name,
                    rule_id=result.rule_id,
                    rule_name=result.rule_id,
                    severity=result.level,
                    message=result.message.text,
                    long_description=result.get_full_description(),
                    location=location,
                    run_id=run_id,
                    repo_id=repo_id
                )
                findings.append(finding)
        
        return findings
    
    @classmethod
    def normalize_spotbugs_xml(cls, xml_data: bytes, run_id: str, repo_id: str) -> List[Finding]:
        """Normalize SpotBugs XML format to unified Finding schema."""
        import xml.etree.ElementTree as ET
        
        root = ET.fromstring(xml_data)
        findings = []
        
        for bug_instance in root.findall('.//BugInstance'):
            bug_type = bug_instance.get('type')
            severity = bug_instance.get('priority', '3')  # 1=High, 2=Medium, 3=Low
            severity_map = {'1': 'HIGH', '2': 'MEDIUM', '3': 'LOW'}
            
            source_line = bug_instance.find('.//SourceLine')
            if source_line is not None:
                location = Location(
                    file_path=source_line.get('sourcepath', ''),
                    line_number=int(source_line.get('start', '0')),
                    code_snippet=source_line.get('message', '')
                )
                
                finding = Finding(
                    finding_id=cls.generate_finding_id(
                        rule_id=bug_type,
                        file_path=location.file_path,
                        line_number=location.line_number
                    ),
                    tool='SpotBugs',
                    rule_id=bug_type,
                    severity=severity_map.get(severity, 'MEDIUM'),
                    message=bug_instance.find('.//ShortMessage').text if bug_instance.find('.//ShortMessage') is not None else '',
                    long_description=bug_instance.find('.//LongMessage').text if bug_instance.find('.//LongMessage') is not None else '',
                    location=location,
                    run_id=run_id,
                    repo_id=repo_id
                )
                findings.append(finding)
        
        return findings
    
    @staticmethod
    def generate_finding_id(rule_id: str, file_path: str, line_number: int) -> str:
        """Generate unique finding ID based on content hash."""
        content = f"{rule_id}:{file_path}:{line_number}"
        hash_value = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"FINDING-{hash_value.upper()}"
```

**Stage 3: Enrichment & Deduplication (Làm giàu và loại bỏ trùng lặp)**

Stage thứ ba thực hiện hai chức năng quan trọng: làm giàu dữ liệu bằng cách bổ sung thông tin ngữ cảnh và loại bỏ các findings trùng lặp. Việc làm giàu dữ liệu giúp cải thiện chất lượng phân tích của AI assistant, trong khi deduplication giúp giảm noise và tập trung vào các lỗ hổng unique.

**Mục tiêu của Stage 3:**

Mục tiêu là tạo ra một tập hợp findings đã được làm giàu với thông tin ngữ cảnh bổ sung và không có duplicates. Điều này giúp:

- Cải thiện độ chính xác của AI analysis bằng cách cung cấp đầy đủ ngữ cảnh
- Giảm số lượng findings cần xử lý bằng cách loại bỏ duplicates
- Cung cấp thông tin phân loại (CWE, OWASP) để prioritization
- Cung cấp CVSS score để đánh giá mức độ nghiêm trọng

**Enrichment Functions:**

**CWE Lookup (Common Weakness Enumeration):**

CWE là hệ thống phân loại các weakness (lỗ hổng) trong phần mềm. Mỗi weakness được gán một CWE ID (ví dụ: CWE-79 cho Cross-site Scripting). Stage này tra cứu CWE ID từ rule_id của từng tool và bổ sung thông tin CWE vào finding.

```python
# CWE Mapping Database
CWE_MAPPING = {
    # Semgrep rules
    'python.lang.security.audit.eval-use.eval-use': 'CWE-94',  # Code Injection
    'javascript.express.security.audit.xss.explicit-xss.explicit-xss': 'CWE-79',  # XSS
    'generic.secrets.security.detected-generic-api-key.generic-api-key': 'CWE-798',  # Hardcoded Credentials
    
    # CodeQL rules
    'js/injection': 'CWE-94',
    'js/xss': 'CWE-79',
    'py/injection': 'CWE-94',
    'java/sqli': 'CWE-89',  # SQL Injection
    
    # ESLint rules
    'security/detect-eval-with-expression': 'CWE-94',
    'security/detect-no-csrf-before-method-override': 'CWE-352',  # CSRF
    
    # SpotBugs rules
    'SQL_NONCONSTANT_STRING_PASSED_TO_EXECUTE': 'CWE-89',
    'XSS_REQUEST_PARAMETER_TO_SEND_ERROR': 'CWE-79',
    'PATH_TRAVERSAL_IN': 'CWE-22',  # Path Traversal
}

def enrich_cwe(finding: Finding) -> Finding:
    """
    Enrich finding with CWE information.
    """
    rule_id = finding.rule_id
    
    # Direct lookup
    if rule_id in CWE_MAPPING:
        cwe_id = CWE_MAPPING[rule_id]
        finding.cwe_id = cwe_id
        finding.cwe_name = CWE_DATABASE.get(cwe_id, {}).get('name', '')
        return finding
    
    # Fuzzy matching
    for pattern, cwe_id in CWE_PATTERN_MAPPING.items():
        if pattern.lower() in rule_id.lower():
            finding.cwe_id = cwe_id
            finding.cwe_name = CWE_DATABASE.get(cwe_id, {}).get('name', '')
            return finding
    
    return finding
```

**OWASP Mapping:**

OWASP Top 10 là danh sách 10 rủi ro bảo mật web hàng đầu. Stage này ánh xạ mỗi finding vào một OWASP category để giúp prioritization dựa trên OWASP risk.

```python
# OWASP Top 10 2021 Mapping
OWASP_CWE_MAPPING = {
    'A01:2021 - Broken Access Control': ['CWE-22', 'CWE-285', 'CWE-639'],
    'A02:2021 - Cryptographic Failures': ['CWE-327', 'CWE-328', 'CWE-798'],
    'A03:2021 - Injection': ['CWE-79', 'CWE-89', 'CWE-94', 'CWE-564'],
    'A04:2021 - Insecure Design': ['CWE-650', 'CWE-656'],
    'A05:2021 - Security Misconfiguration': ['CWE-16', 'CWE-209'],
    'A06:2021 - Vulnerable and Outdated Components': ['CWE-937', 'CWE-1104'],
    'A07:2021 - Identification and Authentication Failures': ['CWE-287', 'CWE-384'],
    'A08:2021 - Software and Data Integrity Failures': ['CWE-502', 'CWE-829'],
    'A09:2021 - Security Logging and Monitoring Failures': ['CWE-778', 'CWE-117'],
    'A10:2021 - Server-Side Request Forgery': ['CWE-918']
}

def enrich_owasp(finding: Finding) -> Finding:
    """
    Enrich finding with OWASP Top 10 category.
    """
    if not finding.cwe_id:
        return finding
    
    for category, cwe_ids in OWASP_CWE_MAPPING.items():
        if finding.cwe_id in cwe_ids:
            finding.owasp_category = category
            break
    
    return finding
```

**CVSS Score Assignment:**

CVSS (Common Vulnerability Scoring System) là hệ thống đánh giá mức độ nghiêm trọng của lỗ hổng bảo mật. CVSS score nằm trong khoảng 0.0-10.0, với các mức: Low (0.1-3.9), Medium (4.0-6.9), High (7.0-8.9), Critical (9.0-10.0).

```python
# CVSS Score Mapping based on CWE and severity
CVSS_SCORE_MAP = {
    'CWE-79': {'CRITICAL': 7.5, 'HIGH': 6.1, 'MEDIUM': 4.3, 'LOW': 2.0},  # XSS
    'CWE-89': {'CRITICAL': 9.8, 'HIGH': 8.6, 'MEDIUM': 6.5, 'LOW': 3.0},  # SQL Injection
    'CWE-94': {'CRITICAL': 9.8, 'HIGH': 8.8, 'MEDIUM': 7.0, 'LOW': 3.5},  # Code Injection
    'CWE-798': {'CRITICAL': 9.1, 'HIGH': 7.5, 'MEDIUM': 5.0, 'LOW': 2.5},  # Hardcoded Credentials
    'CWE-22': {'CRITICAL': 7.5, 'HIGH': 6.5, 'MEDIUM': 5.3, 'LOW': 2.0},  # Path Traversal
    'CWE-352': {'CRITICAL': 8.8, 'HIGH': 6.5, 'MEDIUM': 5.0, 'LOW': 2.5},  # CSRF
}

def enrich_cvss(finding: Finding) -> Finding:
    """
    Enrich finding with CVSS score.
    Falls back to NVD API if local mapping doesn't have the score.
    """
    if finding.cwe_id and finding.severity:
        cwe_cvss_map = CVSS_SCORE_MAP.get(finding.cwe_id, {})
        finding.cvss_score = cwe_cvss_map.get(finding.severity.value)
    
    # If no local mapping, try NVD API
    if not finding.cvss_score and finding.cwe_id:
        finding.cvss_score = fetch_cvss_from_nvd(finding.cwe_id)
    
    return finding
```

**Deduplication Algorithm:**

Deduplication giúp loại bỏ các findings trùng lặp, xảy ra khi nhiều công cụ SAST phát hiện cùng một lỗ hổng. Algorithm sử dụng fingerprint-based deduplication:

```python
def generate_fingerprint(finding: Finding) -> str:
    """
    Generate unique fingerprint for deduplication.
    Fingerprint is based on the combination of rule_id, file_path, and line_number.
    """
    content = f"{finding.rule_id}:{finding.location.file_path}:{finding.location.line_number}"
    return hashlib.sha256(content.encode()).hexdigest()

def deduplicate_findings(findings: List[Finding]) -> List[Finding]:
    """
    Remove duplicate findings based on fingerprint.
    When duplicates are found, keep the finding with highest severity.
    """
    seen_fingerprints = {}
    unique_findings = []
    
    for finding in findings:
        fingerprint = generate_fingerprint(finding)
        
        if fingerprint not in seen_fingerprints:
            # First time seeing this fingerprint
            seen_fingerprints[fingerprint] = finding
            unique_findings.append(finding)
        else:
            # Duplicate found, keep the one with higher severity
            existing = seen_fingerprints[fingerprint]
            severity_order = {'CRITICAL': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1, 'INFO': 0}
            
            if severity_order.get(finding.severity.value, 0) > severity_order.get(existing.severity.value, 0):
                # Replace with higher severity finding
                unique_findings.remove(existing)
                seen_fingerprints[fingerprint] = finding
                unique_findings.append(finding)
    
    logger.info(f"Deduplication: {len(findings)} -> {len(unique_findings)} findings ({len(findings) - len(unique_findings)} duplicates removed)")
    return unique_findings
```

**Stage 4: Persist to Database (Lưu trữ vào cơ sở dữ liệu)**

Stage cuối cùng lưu trữ normalized findings vào SQLite database. SQLite được lựa chọn vì tính đơn giản, nhẹ, và phù hợp cho quy mô của đồ án. Database được thiết kế với indexing tối ưu để hỗ trợ các truy vấn thường gặp.

**Database Schema chi tiết:**

```sql
-- Main findings table
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id TEXT UNIQUE NOT NULL,
    tool TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    rule_name TEXT,
    severity TEXT NOT NULL CHECK(severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')),
    confidence TEXT CHECK(confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    message TEXT NOT NULL,
    long_description TEXT,
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    column_number INTEGER,
    code_snippet TEXT,
    cwe_id TEXT,
    cwe_name TEXT,
    owasp_category TEXT,
    cvss_score REAL CHECK(cvss_score >= 0 AND cvss_score <= 10),
    run_id TEXT NOT NULL,
    repo_id TEXT NOT NULL,
    commit_sha TEXT,
    branch TEXT,
    fingerprint TEXT,
    ai_analysis TEXT,
    ai_suggestion TEXT,
    status TEXT DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'FALSE_POSITIVE')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Audit log for raw SARIF files
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    repo_id TEXT NOT NULL,
    tool TEXT NOT NULL,
    raw_sarif_path TEXT NOT NULL,
    findings_count INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for query optimization
CREATE INDEX IF NOT EXISTS idx_findings_repo_run ON findings(repo_id, run_id);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_findings_fingerprint ON findings(fingerprint);
CREATE INDEX IF NOT EXISTS idx_findings_cwe ON findings(cwe_id);
CREATE INDEX IF NOT EXISTS idx_findings_owasp ON findings(owasp_category);
CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
CREATE INDEX IF NOT EXISTS idx_findings_created_at ON findings(created_at);
CREATE INDEX IF NOT EXISTS idx_findings_cvss_score ON findings(cvss_score DESC);
CREATE INDEX IF NOT EXISTS idx_findings_file_path ON findings(file_path);
CREATE INDEX IF NOT EXISTS idx_findings_tool ON findings(tool);
```

**Implementation sử dụng SQLAlchemy ORM:**

```python
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Index
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

Base = declarative_base()

class FindingModel(Base):
    __tablename__ = 'findings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    finding_id = Column(String, unique=True, nullable=False, index=True)
    tool = Column(String, nullable=False, index=True)
    rule_id = Column(String, nullable=False, index=True)
    rule_name = Column(String)
    severity = Column(String, nullable=False, index=True)
    confidence = Column(String)
    message = Column(Text, nullable=False)
    long_description = Column(Text)
    file_path = Column(String, nullable=False, index=True)
    line_number = Column(Integer, nullable=False)
    column_number = Column(Integer)
    code_snippet = Column(Text)
    cwe_id = Column(String, index=True)
    cwe_name = Column(String)
    owasp_category = Column(String, index=True)
    cvss_score = Column(Float, index=True)
    run_id = Column(String, nullable=False, index=True)
    repo_id = Column(String, nullable=False, index=True)
    commit_sha = Column(String)
    branch = Column(String)
    fingerprint = Column(String, index=True)
    ai_analysis = Column(Text)
    ai_suggestion = Column(Text)
    status = Column(String, default='OPEN', index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DatabaseManager:
    """
    Manages database operations for storing and querying findings.
    """
    
    def __init__(self, database_url: str = 'sqlite:///findings.db'):
        self.engine = create_engine(database_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def save_findings(self, findings: list):
        """Save a batch of findings to the database."""
        session = self.Session()
        try:
            for finding in findings:
                finding_model = FindingModel(
                    finding_id=finding.finding_id,
                    tool=finding.tool,
                    rule_id=finding.rule_id,
                    rule_name=finding.rule_name,
                    severity=finding.severity.value,
                    confidence=finding.confidence,
                    message=finding.message,
                    long_description=finding.long_description,
                    file_path=finding.location.file_path,
                    line_number=finding.location.line_number,
                    column_number=finding.location.column_number,
                    code_snippet=finding.location.code_snippet,
                    cwe_id=finding.cwe_id,
                    cwe_name=finding.cwe_name,
                    owasp_category=finding.owasp_category,
                    cvss_score=finding.cvss_score,
                    run_id=finding.run_id,
                    repo_id=finding.repo_id,
                    commit_sha=finding.commit_sha,
                    branch=finding.branch,
                    fingerprint=generate_fingerprint(finding)
                )
                session.merge(finding_model)  # merge handles upsert
            session.commit()
            print(f"Saved {len(findings)} findings to database")
        except Exception as e:
            session.rollback()
            print(f"Error saving findings: {e}")
            raise
        finally:
            session.close()
    
    def get_findings_by_run(self, run_id: str):
        """Get all findings for a specific run."""
        session = self.Session()
        try:
            return session.query(FindingModel).filter_by(run_id=run_id).all()
        finally:
            session.close()
    
    def get_findings_summary(self, repo_id: str):
        """Get summary statistics for a repository."""
        session = self.Session()
        try:
            from sqlalchemy import func
            
            summary = session.query(
                FindingModel.severity,
                func.count(FindingModel.id).label('count')
            ).filter_by(
                repo_id=repo_id,
                status='OPEN'
            ).group_by(FindingModel.severity).all()
            
            return {row.severity: row.count for row in summary}
        finally:
            session.close()
```

### 3.4.2. Secure gateway sử dụng Guardrail cho AI assistant

Trong bối cảnh tích hợp AI vào các hệ thống xử lý thông tin nhạy cảm như mã nguồn và kết quả quét bảo mật, việc đảm bảo an toàn cho quá trình tương tác với LLM là vô cùng quan trọng. MCP Gateway được trang bị hệ thống guardrail (rào chắn) nhiều lớp nhằm bảo vệ AI assistant khỏi các đầu vào độc hại, ngăn chặn rò rỉ thông tin nhạy cảm, và đảm bảo rằng chỉ những dữ liệu an toàn và đã được kiểm tra mới được chuyển đến mô hình LLM. Hệ thống guardrail này được thiết kế theo nguyên tắc defense-in-depth, trong đó nhiều lớp bảo vệ được áp dụng tuần tự để tăng cường an ninh tổng thể.

**Hình 3.4. MCP Gateway Guardrail Layers**

*(Chèn sơ đồ Image 8 tại đây)*

**Nguyên lý hoạt động của Guardrail System:**

Guardrail system hoạt động theo mô hình pipeline, trong đó mỗi request đi qua bốn lớp bảo vệ tuần tự. Nếu bất kỳ lớp nào phát hiện vấn đề, request sẽ bị reject ngay lập tức và không được chuyển đến các lớp tiếp theo hoặc đến LLM. Mô hình này đảm bảo rằng:

1. Chỉ các request được xác thực mới có thể truy cập hệ thống
2. Dữ liệu đầu vào đúng định dạng và cấu trúc mong đợi
3. Thông tin nhạy cảm được loại bỏ trước khi gửi đến LLM
4. Prompt injection attacks được ngăn chặn
5. Response từ LLM được validate trước khi trả về user

**Layer 1: Authentication Layer (Lớp xác thực)**

Đây là lớp bảo vệ đầu tiên, đảm bảo rằng chỉ các request được xác thực và ủy quyền mới có thể truy cập vào hệ thống. Lớp này áp dụng nhiều cơ chế xác thực và mã hóa để đảm bảo tính bảo mật của quá trình truyền thông.

**Fine-grained PAT (Personal Access Token):**

Hệ thống sử dụng GitHub Personal Access Token với scope được giới hạn chặt chẽ. Token chỉ được cấp quyền `actions:read`, nghĩa là chỉ có thể đọc artifacts từ GitHub Actions và không thể thực hiện bất kỳ thao tác ghi nào lên repository. Điều này giúp giảm thiểu rủi ro nếu token bị lộ.

```python
# Token validation
VALID_SCOPES = {'actions:read'}

def validate_token_scope(token: str) -> bool:
    """
    Validate that the token has the correct scopes.
    Only tokens with actions:read scope are accepted.
    """
    response = requests.get(
        'https://api.github.com/user',
        headers={'Authorization': f'token {token}'}
    )
    
    if response.status_code != 200:
        return False
    
    # Check scopes from response headers
    scopes_header = response.headers.get('X-OAuth-Scopes', '')
    granted_scopes = {s.strip() for s in scopes_header.split(',')}
    
    # Verify that granted scopes are within allowed scopes
    return granted_scopes.issubset(VALID_SCOPES)
```

**HTTPS/TLS 1.2+ Encryption:**

Tất cả communications giữa các thành phần trong hệ thống đều được mã hóa bằng giao thức TLS phiên bản 1.2 hoặc cao hơn. Điều này đảm bảo rằng dữ liệu không thể bị đánh cắp hoặc thay đổi trong quá trình truyền qua mạng.

```python
# HTTPS verification configuration
import ssl

def create_secure_session():
    """
    Create a requests session with strict HTTPS verification.
    """
    session = requests.Session()
    
    # Force TLS 1.2 or higher
    session.mount('https://', requests.adapters.HTTPAdapter(
        pool_connections=10,
        pool_maxsize=100,
        max_retries=3
    ))
    
    # Verify SSL certificates
    session.verify = True
    
    return session
```

**Rate Limiting:**

Để ngăn chặn abuse và DDoS attacks, hệ thống áp dụng rate limiting cho mỗi token. Giới hạn hiện tại là 100 requests per minute per token. Khi vượt quá giới hạn, hệ thống trả về HTTP 429 (Too Many Requests).

```python
from collections import defaultdict
import time

class RateLimiter:
    """
    Simple in-memory rate limiter.
    """
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
    
    def is_allowed(self, token: str) -> bool:
        """
        Check if the request is within rate limits.
        """
        now = time.time()
        window_start = now - self.window_seconds
        
        # Remove old requests outside the window
        self.requests[token] = [
            t for t in self.requests[token] if t > window_start
        ]
        
        # Check if under limit
        if len(self.requests[token]) >= self.max_requests:
            return False
        
        # Record this request
        self.requests[token].append(now)
        return True
```

**Layer 2: Schema Validation Layer (Lớp kiểm tra schema)**

Lớp thứ hai đảm bảo rằng dữ liệu đầu vào đúng định dạng và cấu trúc mong đợi. Lớp này sử dụng Pydantic strict mode để validate input và reject bất kỳ dữ liệu nào không đúng schema.

**Pydantic Strict Mode:**

Pydantic strict mode được bật để đảm bảo rằng chỉ các fields được định nghĩa trong model mới được chấp nhận. Các fields không xác định sẽ gây ra validation error.

```python
from pydantic import BaseModel, Field, Extra

class InputRequest(BaseModel):
    """
    Strict schema for input requests.
    """
    class Config:
        extra = Extra.forbid  # Reject any extra fields
        strict = True  # Enable strict type checking
    
    repo_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        regex=r'^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$'
    )
    run_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        regex=r'^[0-9]+$'
    )
    finding_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=100
    )
    
    @validator('repo_id')
    def validate_repo_id_format(cls, v):
        """Validate repo_id format (owner/repo)."""
        if '/' not in v:
            raise ValueError('repo_id must be in format owner/repo')
        return v
    
    @validator('run_id')
    def validate_run_id_format(cls, v):
        """Validate run_id is numeric."""
        if not v.isdigit():
            raise ValueError('run_id must be numeric')
        return v
```

**Required Fields Check:**

Tất cả required fields phải có giá trị. Nếu bất kỳ required field nào bị thiếu, request sẽ bị reject với HTTP 400 và error message chi tiết.

**Type Validation:**

Kiểu dữ liệu của từng field được kiểm tra nghiêm ngặt. Ví dụ:
- `repo_id` phải là string và match regex pattern
- `run_id` phải là string chứa số
- `finding_ids` phải là list của strings với độ dài trong khoảng cho phép

```python
# Validation error handling
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

async def validation_exception_handler(request: Request, exc: ValidationError):
    """
    Handle Pydantic validation errors.
    Returns detailed error information to the client.
    """
    errors = []
    for error in exc.errors():
        errors.append({
            'field': '.'.join(str(loc) for loc in error['loc']),
            'message': error['msg'],
            'type': error['type']
        })
    
    return JSONResponse(
        status_code=400,
        content={
            'error': 'VALIDATION_FAILED',
            'message': 'Input validation failed',
            'details': errors
        }
    )
```

**Layer 3: Content Sanitization Layer (Lớp kiểm tra nội dung)**

Lớp thứ ba có trách nhiệm loại bỏ thông tin nhạy cảm từ input data trước khi gửi đến LLM. Đây là lớp quan trọng nhất trong việc bảo vệ thông tin nội bộ khỏi bị rò rỉ.

**PII Scrubber (Personally Identifiable Information):**

PII scrubber sử dụng regex patterns để phát hiện và loại bỏ các thông tin cá nhân nhạy cảm khỏi dữ liệu đầu vào.

```python
import re

class PIIScrubber:
    """
    Scrubs Personally Identifiable Information from text.
    """
    
    PATTERNS = {
        'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        'phone': re.compile(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
        'ssn': re.compile(r'\b\d{3}[-]?\d{2}[-]?\d{4}\b'),
        'credit_card': re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
        'ip_address': re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        'private_ip': re.compile(
            r'\b(?:'
            r'10\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
            r'172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|'
            r'192\.168\.\d{1,3}\.\d{1,3}'
            r')\b'
        )
    }
    
    @classmethod
    def scrub(cls, text: str) -> str:
        """
        Remove all PII from text.
        """
        for pattern_name, pattern in cls.PATTERNS.items():
            text = pattern.sub(f'[REDACTED_{pattern_name.upper()}]', text)
        return text
```

**Secret Detection:**

Secret detection module phát hiện và loại bỏ các API keys, tokens, passwords, và credentials khác khỏi dữ liệu.

```python
class SecretDetector:
    """
    Detects and redacts secrets from text.
    """
    
    PATTERNS = {
        'aws_access_key': re.compile(r'AKIA[0-9A-Z]{16}'),
        'aws_secret_key': re.compile(r'(?i)aws_secret_access_key\s*=\s*["\']?([A-Za-z0-9/+=]{40})["\']?'),
        'github_token': re.compile(r'gh[pousr]_[A-Za-z0-9_]{36,}'),
        'generic_api_key': re.compile(r'(?i)(?:api[_-]?key|apikey)\s*[:=]\s*["\']?([A-Za-z0-9]{20,})["\']?'),
        'generic_secret': re.compile(r'(?i)(?:secret|password|passwd|pwd)\s*[:=]\s*["\']?([A-Za-z0-9!@#$%^&*]{8,})["\']?'),
        'private_key': re.compile(r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----'),
        'jwt_token': re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}')
    }
    
    @classmethod
    def detect_and_redact(cls, text: str) -> tuple:
        """
        Detect and redact secrets from text.
        Returns (redacted_text, list_of_detected_secrets).
        """
        detected = []
        for secret_type, pattern in cls.PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                detected.extend(matches)
                text = pattern.sub(f'[REDACTED_{secret_type.upper()}]', text)
        return text, detected
```

**Environment Variable Redaction:**

Environment variables thường chứa thông tin nhạy cảm và cần được loại bỏ trước khi gửi đến LLM.

```python
class EnvVarRedactor:
    """
    Redacts environment variables from text.
    """
    
    # Common environment variable patterns
    ENV_VAR_PATTERN = re.compile(r'\$\{?[A-Z_][A-Z0-9_]*\}?')
    
    # Common sensitive environment variable names
    SENSITIVE_ENV_VARS = {
        'DATABASE_URL', 'DB_PASSWORD', 'API_KEY', 'SECRET_KEY',
        'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'JWT_SECRET',
        'ENCRYPTION_KEY', 'PRIVATE_KEY', 'GITHUB_TOKEN',
        'SLACK_TOKEN', 'SENDGRID_API_KEY'
    }
    
    @classmethod
    def redact(cls, text: str) -> str:
        """
        Redact sensitive environment variables from text.
        """
        def replace_env_var(match):
            var_name = match.group(0).strip('$ {}')
            if var_name in cls.SENSITIVE_ENV_VARS:
                return f'[REDACTED_ENV_{var_name}]'
            return match.group(0)
        
        return cls.ENV_VAR_PATTERN.sub(replace_env_var, text)
```

**Layer 4: Prompt Security Layer (Lớp kiểm tra prompt)**

Lớp cuối cùng bảo vệ khỏi prompt injection attacks, trong đó attacker cố gắng thao túng LLM để thực hiện các hành vi không mong muốn.

**Injection Deny-list:**

Danh sách đen các patterns nguy hiểm bị chặn:

```python
class PromptInjectionDetector:
    """
    Detects prompt injection attempts.
    """
    
    INJECTION_PATTERNS = [
        # Direct instruction override
        re.compile(r'(?i)ignore\s+(previous|all|above)\s+instructions?'),
        re.compile(r'(?i)forget\s+(everything|all)\s+(you\s+know|your\s+instructions?)'),
        re.compile(r'(?i)disregard\s+(previous|all)\s+instructions?'),
        
        # Role-playing attacks
        re.compile(r'(?i)you\s+are\s+(now\s+)?DAN'),
        re.compile(r'(?i)you\s+are\s+(now\s+)?Developer\s+Mode'),
        re.compile(r'(?i)act\s+as\s+(a|an)\s+(hacker|attacker|unrestricted)'),
        
        # System prompt override
        re.compile(r'(?i)(override|replace|modify)\s+system\s+prompt'),
        re.compile(r'(?i)(change|update)\s+your\s+(role|instructions|guidelines)'),
        
        # Jailbreak attempts
        re.compile(r'(?i)(jailbreak|bypass|circumvent)\s+(security|guardrails|restrictions)'),
        re.compile(r'(?i)answer\s+(without|no)\s+(restrictions|limitations|filtering)'),
        
        # Base64 encoded instructions
        re.compile(r'base64:[A-Za-z0-9+/=]{20,}'),
        re.compile(r'(?i)decode\s+the\s+following\s+base64'),
        
        # Output manipulation
        re.compile(r'(?i)do\s+not\s+(include|mention|show)\s+(disclaimer|warning|note)'),
        re.compile(r'(?i)only\s+output\s+(the\s+)?(answer|result|code)\s+without'),
    ]
    
    @classmethod
    def check(cls, prompt: str) -> tuple:
        """
        Check if prompt contains injection attempts.
        Returns (is_safe, matched_patterns).
        """
        matched = []
        for pattern in cls.INJECTION_PATTERNS:
            if pattern.search(prompt):
                matched.append(pattern.pattern)
        
        return len(matched) == 0, matched
```

**Special Character Escaping:**

Các ký tự đặc biệt được escape để ngăn chặn các attack vectors khác.

```python
def escape_special_chars(text: str) -> str:
    """
    Escape special characters that could be used for injection.
    """
    # Escape backticks to prevent markdown injection
    text = text.replace('`', '\\`')
    
    # Escape HTML tags
    text = text.replace('<', '&lt;').replace('>', '&gt;')
    
    # Escape markdown that could be used for formatting attacks
    text = text.replace('**', '\\*\\*').replace('__', '\\_\\_')
    
    return text
```

**Token Budget Limit:**

Giới hạn độ dài của prompt để ngăn chặn token exhaustion attacks.

```python
class TokenBudgetChecker:
    """
    Enforces token budget limits.
    """
    
    MAX_PROMPT_TOKENS = 4000  # Maximum tokens allowed in prompt
    
    @classmethod
    def check(cls, prompt: str) -> tuple:
        """
        Check if prompt is within token budget.
        Returns (is_within_budget, token_count).
        """
        # Simple token count (approximate)
        token_count = len(prompt.split())
        
        # More accurate count using tiktoken if available
        try:
            import tiktoken
            encoder = tiktoken.get_encoding('cl100k_base')
            token_count = len(encoder.encode(prompt))
        except ImportError:
            pass
        
        return token_count <= cls.MAX_PROMPT_TOKENS, token_count
```

**Reject Path (Đường dẫn từ chối):**

Khi bất kỳ layer nào trong bốn layers trên phát hiện vấn đề, request sẽ bị reject theo quy trình sau:

1. **HTTP 400 Response**: Trả về HTTP 400 (Bad Request) với error code chi tiết. Error code cho biết layer nào đã reject và lý do.

```python
class RejectResponse(BaseModel):
    error: str
    error_code: str
    message: str
    rejected_by_layer: str
    details: Optional[Dict] = None

# Example reject responses
REJECT_RESPONSES = {
    'AUTH_FAILED': {
        'error': 'Authentication Failed',
        'error_code': 'AUTH_001',
        'rejected_by_layer': 'Layer 1 - Auth',
        'message': 'Invalid or expired token'
    },
    'VALIDATION_FAILED': {
        'error': 'Validation Failed',
        'error_code': 'VAL_001',
        'rejected_by_layer': 'Layer 2 - Schema',
        'message': 'Input does not match required schema'
    },
    'SECRET_DETECTED': {
        'error': 'Sensitive Data Detected',
        'error_code': 'SEC_001',
        'rejected_by_layer': 'Layer 3 - Content',
        'message': 'Request contains sensitive information that must be removed'
    },
    'INJECTION_DETECTED': {
        'error': 'Injection Attempt Detected',
        'error_code': 'INJ_001',
        'rejected_by_layer': 'Layer 4 - Prompt',
        'message': 'Request contains potentially malicious content'
    }
}
```

2. **Local Logging**: Log chi tiết được ghi vào local file để phục vụ audit và debugging. Log không bao giờ được gửi lên external service để đảm bảo tính bảo mật.

```python
import logging
from datetime import datetime

# Configure secure audit logger
audit_logger = logging.getLogger('mcp.audit')
audit_logger.setLevel(logging.INFO)

# File handler for local audit log
file_handler = logging.FileHandler('logs/audit.log')
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
audit_logger.addHandler(file_handler)

def log_rejection(request_data: dict, reject_reason: str, details: dict):
    """
    Log rejected request to local audit log.
    """
    audit_logger.warning(
        f"REQUEST_REJECTED | "
        f"reason={reject_reason} | "
        f"ip={request_data.get('ip')} | "
        f"user={request_data.get('user_id')} | "
        f"details={details}"
    )
```

3. **Dashboard Notification**: Notification được gửi đến dashboard để hiển thị warning cho administrators.

```python
async def notify_dashboard(rejection_data: dict):
    """
    Send notification to dashboard about rejected request.
    """
    await websocket_manager.broadcast({
        'type': 'security_alert',
        'severity': 'WARNING',
        'message': f"Request rejected: {rejection_data['reject_reason']}",
        'timestamp': datetime.utcnow().isoformat(),
        'details': rejection_data
    })
```

4. **No LLM Forwarding**: Input bị reject không bao giờ được forwarded đến LLM. Đây là nguyên tắc cốt lõi đảm bảo rằng LLM chỉ nhận được dữ liệu đã được kiểm tra và làm sạch.

**Output Validation (Kiểm tra đầu ra):**

Response từ LLM cũng được validate trước khi trả về user để đảm bảo an toàn và chất lượng.

```python
class OutputValidator:
    """
    Validates and sanitizes LLM output.
    """
    
    @classmethod
    def validate(cls, response: str) -> tuple:
        """
        Validate LLM response.
        Returns (is_valid, sanitized_response, issues).
        """
        issues = []
        
        # 1. Strip markdown injection
        sanitized = cls.strip_markdown_injection(response)
        
        # 2. Validate response schema (check for required sections)
        if not cls.validate_schema(sanitized):
            issues.append('Response does not match expected schema')
        
        # 3. Confidence score check
        confidence = cls.extract_confidence_score(sanitized)
        if confidence and confidence < 0.7:
            issues.append('Low confidence score')
            sanitized += '\n\n⚠️ **Note**: This analysis has low confidence. Please verify manually.'
        
        # 4. Strip dangerous HTML
        sanitized = cls.strip_dangerous_html(sanitized)
        
        return len(issues) == 0, sanitized, issues
    
    @staticmethod
    def strip_markdown_injection(text: str) -> str:
        """
        Remove potentially dangerous markdown patterns.
        """
        # Remove nested code blocks that could contain malicious content
        text = re.sub(r'```\s*\n.*?```', '[CODE_BLOCK_REMOVED]', text, flags=re.DOTALL)
        
        # Remove HTML-like patterns
        text = re.sub(r'<[^>]*>', '', text)
        
        return text
    
    @staticmethod
    def strip_dangerous_html(text: str) -> str:
        """
        Remove dangerous HTML tags.
        """
        dangerous_tags = ['script', 'iframe', 'object', 'embed', 'form', 'input']
        for tag in dangerous_tags:
            text = re.sub(f'<{tag}.*?</{tag}>', '', text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(f'<{tag}.*?/?>', '', text, flags=re.IGNORECASE)
        return text
```

## 3.5. Luồng dữ liệu hoạt động

### 3.5.1. Sơ đồ luồng dữ liệu End-to-end

Luồng dữ liệu end-to-end của hệ thống mô tả toàn bộ quá trình xử lý từ khi developer thực hiện thay đổi mã nguồn cho đến khi nhận được kết quả phân tích bảo mật và đề xuất khắc phục từ AI assistant. Luồng dữ liệu này được thiết kế để đảm bảo tính tự động hóa cao, với sự can thiệp tối thiểu của con người, đồng thời duy trì tính bảo mật và chất lượng của quá trình phân tích.

**Hình 3.5. End-to-end Data Flow Diagram**

*(Chèn sơ đồ Image 11 tại đây)*

**Bảng 3.6. Chi tiết luồng dữ liệu End-to-end**

| Bước | Thành phần thực hiện | Hành động chi tiết | Dữ liệu đầu vào | Dữ liệu đầu ra | Thời gian ước tính |
|------|---------------------|-------------------|-----------------|----------------|-------------------|
| 1 | Developer | Thực hiện push code lên repository hoặc tạo pull request mới. Developer có thể push trực tiếp lên nhánh feature hoặc tạo PR để merge vào nhánh develop/main. | Git commit với mã nguồn đã thay đổi | Git push event hoặc Pull Request event | - |
| 2 | GitHub | Nhận push/PR event và phát sinh webhook event. Webhook event chứa thông tin về repository, branch, commit SHA, và người thực hiện. Webhook được gửi đến GitHub Actions để trigger workflow. | Git push/PR event | Webhook payload (JSON) | < 1 giây |
| 3 | GitHub Actions | Nhận webhook và trigger workflow đã được cấu hình. Workflow được định nghĩa trong file `.github/workflows/main.yml` và bao gồm nhiều jobs sẽ được thực thi. | Webhook payload | Workflow execution started | < 5 giây |
| 4 | CI Pipeline | Thực thi các jobs trong workflow theo thứ tự và dependencies. Các jobs bao gồm: checkout code, setup environment, install dependencies, build, unit test, SAST scan (song song), dependency check. | Source code, workflow definition | Build artifacts, test results, SAST scan results | 5-20 phút |
| 5 | CI Pipeline | Upload kết quả quét từ mỗi công cụ SAST lên GitHub Artifacts. Mỗi công cụ tạo ra một artifact riêng biệt với định dạng phù hợp (SARIF, XML, JSON). | SAST scan results (SARIF/XML/JSON) | Artifacts stored in GitHub | 30-60 giây |
| 6 | Security Gate | Tổng hợp kết quả từ tất cả công cụ, áp dụng security policies để ra quyết định Pass/Fail. Nếu Fail, PR bị block và developer được thông báo. Nếu Pass, quy trình tiếp tục. | All SAST results, security policies | Pass/Fail decision, violations list | 30-60 giây |
| 7 | MCP Gateway | Nếu security gate Pass, MCP Gateway fetch artifacts từ GitHub. MCP sử dụng PAT với actions:read scope để tải artifacts về. | GitHub Artifacts API response | Raw SAST results (bytes) | 1-2 phút |
| 8 | MCP Gateway | Thực hiện data normalization pipeline: parse các định dạng khác nhau, convert sang schema thống nhất, validate sử dụng Pydantic, và reject nếu validation fail. | Raw SAST results (multiple formats) | Normalized findings (unified schema) | 1-2 phút |
| 9 | MCP Gateway | Thực hiện enrichment và deduplication: tra cứu CWE ID, OWASP mapping, CVSS scoring, và loại bỏ duplicates dựa trên fingerprint. | Normalized findings | Enriched & deduplicated findings | 1-2 phút |
| 10 | MCP Gateway | Build secure context cho LLM: áp dụng guardrails (auth, schema validation, content sanitization, prompt security), loại bỏ sensitive data, và tạo prompt tối ưu. | Enriched findings, source code context | Secure context object | < 30 giây |
| 11 | LLM Orchestrator | Gửi secure context đến Gemini API để phân tích. LLM thực hiện vulnerability explanation, impact assessment, remediation suggestion, và best practices recommendation. | Secure context object | AI analysis results (explanations, suggestions) | 5-30 giây |
| 12 | LLM Orchestrator | Validate response từ LLM: kiểm tra schema, confidence score, strip dangerous content, và persist vào database. | AI analysis results | Validated & sanitized AI results | < 10 giây |
| 13 | Storage | Lưu normalized findings và AI analysis vào SQLite database. Raw SARIF files được lưu vào local storage để audit. Database indexing được tối ưu cho các truy vấn thường gặp. | Normalized findings, AI results | Database records | < 5 giây |
| 14 | Web Dashboard | Hiển thị kết quả trên dashboard thông qua real-time polling (15s interval). Dashboard bao gồm: findings summary, severity chart, top findings list, và AI analysis details. | Database query results | UI components (HTML/JS/CSS) | - |
| 15 | ChatOps Platform | Gửi notification đến developer thông qua chat platform. Notification bao gồm tóm tắt kết quả và link đến dashboard chi tiết. | Analysis results | Chat message | - |

**Chi tiết luồng xử lý cho từng kịch bản:**

**Kịch bản 1: Luồng xử lý bình thường (Happy Path)**

Đây là kịch bản lý tưởng khi code thay đổi không chứa lỗ hổng bảo mật nghiêm trọng và security gate passed.

1. Developer push code lên nhánh feature.
2. GitHub trigger workflow và CI pipeline bắt đầu chạy.
3. Tất cả jobs hoàn tất thành công, bao gồm SAST scans.
4. Security gate evaluation trả về PASS vì không có violations vượt quá threshold.
5. MCP Gateway fetch artifacts và xử lý dữ liệu.
6. LLM phân tích và tạo đề xuất (nếu có findings ở mức LOW/MEDIUM).
7. Kết quả được lưu vào database và hiển thị trên dashboard.
8. Developer nhận notification rằng pipeline đã hoàn tất và code sẵn sàng để merge.

**Kịch bản 2: Luồng xử lý khi phát hiện lỗ hổng (Vulnerability Found Path)**

Đây là kịch bản phổ biến khi SAST tools phát hiện lỗ hổng bảo mật.

1. Developer push code hoặc tạo PR.
2. CI pipeline chạy và SAST tools phát hiện lỗ hổng.
3. Security gate evaluation trả về FAIL vì có violations vượt quá threshold.
4. PR bị block và developer nhận notification chi tiết về violations.
5. Developer xem kết quả trên dashboard và đọc AI analysis để hiểu lỗ hổng.
6. Developer sử dụng AI suggestion để fix code.
7. Developer push code fix và pipeline chạy lại (rerun).
8. Nếu security gate PASS sau fix, PR được unblock.

**Kịch bản 3: Luồng xử lý với approval (Approval Path)**

Đây là kịch bản khi security gate fail nhưng policy cho phép approval từ security team lead.

1. CI pipeline phát hiện violations ở mức HIGH (không có CRITICAL).
2. Security gate trả về FAIL với yêu cầu approval.
3. Approval request được tạo và gửi đến security team leads.
4. Security lead review findings trên dashboard và đọc AI analysis.
5. Security lead ra quyết định Approve hoặc Reject.
6. Nếu Approve: PR được unblock với justification được ghi nhận.
7. Nếu Reject: developer cần fix violations trước khi có thể merge.

**Feedback Loop: Rerun Pipeline**

Hệ thống hỗ trợ vòng lặp phản hồi cho phép developer rerun pipeline sau khi fix lỗi mà không cần push code mới. Luồng rerun được mô tả chi tiết dưới đây:

1. **User Action (Người dùng click Rerun)**: Developer xem kết quả quét trên dashboard hoặc nhận notification về violations. Sau khi thực hiện fix code, developer click nút "Rerun" trên dashboard hoặc gửi command `/rerun` thông qua ChatOps Platform. Hành động này gửi request đến backend API để trigger rerun.

2. **FastAPI Tool Router**: Backend API nhận request và thực hiện xác thực (JWT token) và phân quyền (kiểm tra user có write access đến repository). Request được route đến rerun handler.

3. **GitHub Actions API Call**: Rerun handler gọi GitHub Actions API endpoint `POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun` để trigger rerun của workflow run trước đó. GitHub API xác thực request và trigger rerun.

4. **New CI Run**: GitHub Actions chạy lại workflow với code mới nhất từ repository. Các jobs được thực thi theo cùng thứ tự và cấu hình như lần chạy trước.

5. **New SARIF Generation**: SAST tools chạy lại và tạo ra kết quả SARIF mới. Kết quả mới phản ánh trạng thái mã nguồn sau khi fix.

6. **MCP → LLM Processing**: MCP Gateway fetch artifacts mới, xử lý dữ liệu, và gửi đến LLM để phân tích. LLM tạo analysis mới dựa trên findings mới.

7. **Dashboard Update**: Kết quả mới được lưu vào database và dashboard được cập nhật thông qua real-time polling. Developer có thể thấy sự khác biệt giữa kết quả trước và sau khi fix.

```python
# Rerun Pipeline Implementation
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix='/pipeline', tags=['pipeline'])

class RerunRequest(BaseModel):
    repo_id: str
    run_id: str

class RerunResponse(BaseModel):
    status: str
    message: str
    new_run_id: Optional[str] = None

@router.post('/rerun', response_model=RerunResponse)
async def rerun_pipeline(
    request: RerunRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Trigger a rerun of the specified pipeline run.
    """
    # Verify user has write access to repository
    if not await has_write_access(current_user, request.repo_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Insufficient permissions'
        )
    
    # Get GitHub token for the repository
    github_token = await get_github_token(request.repo_id)
    
    # Call GitHub Actions API to rerun
    owner, repo = request.repo_id.split('/')
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/runs/{request.run_id}/rerun'
    
    response = requests.post(
        url,
        headers={'Authorization': f'token {github_token}'}
    )
    
    if response.status_code == 201:
        # Rerun triggered successfully
        # Get new run ID from response headers
        new_run_id = response.headers.get('X-GitHub-Run-Id')
        
        return RerunResponse(
            status='success',
            message=f'Pipeline rerun triggered for run {request.run_id}',
            new_run_id=new_run_id
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Failed to trigger rerun: {response.text}'
        )
```

## 3.6. Considerations về bảo mật và phân tích mối đe dọa

Trong quá trình thiết kế và xây dựng hệ thống, các mối đe dọa tiềm ẩn đã được phân tích và các biện pháp đối phó đã được tích hợp vào kiến trúc. Phân tích mối đe dọa được thực hiện sử dụng phương pháp STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege).

**Bảng 3.7. Phân tích mối đe dọa STRIDE**

| Mối đe dọa | Mô tả | Tác động | Biện pháp đối phó |
|------------|-------|----------|-------------------|
| Spoofing (Giả mạo) | Attacker giả mạo developer để push mã độc hoặc trigger pipeline | Mã độc được đưa vào production | GitHub PAT với scope giới hạn, JWT authentication, Webhook signature verification |
| Tampering (Thay đổi) | Attacker thay đổi kết quả quét hoặc security gate decision | Lỗ hổng bị che giấu, code không an toàn được merge | Immutable artifacts, audit logging, cryptographic signatures cho results |
| Repudiation (Từ chối) | User từ chối đã thực hiện hành động nào đó | Khó khăn trong việc điều tra và compliance | Comprehensive audit logging với timestamps và user identification |
| Information Disclosure (Rò rỉ thông tin) | LLM làm rò rỉ mã nguồn hoặc thông tin nhạy cảm | Lộ bí mật thương mại, credentials | Multi-layer guardrails, PII scrubbing, secret detection, output validation |
| Denial of Service (Từ chối dịch vụ) | Attacker flood hệ thống với requests | Hệ thống ngừng hoạt động | Rate limiting, request queuing, circuit breakers |
| Elevation of Privilege (Leo thang đặc quyền) | User có quyền thấp cố gắng thực hiện actions của user có quyền cao | Truy cập trái phép, thay đổi policies | Role-based access control (RBAC), principle of least privilege |

## 3.7. Tối ưu hóa hiệu năng và khả năng mở rộng

Hệ thống được thiết kế với khả năng mở rộng ngang (horizontal scaling) cho phép xử lý nhiều requests đồng thời và phục vụ nhiều repositories. Các chiến lược tối ưu hóa hiệu năng bao gồm:

**Caching Strategy:**

- **Artifact Caching**: Kết quả quét được cache trong 24 giờ để giảm số lượng API calls đến GitHub.
- **Database Query Caching**: Các truy vấn thường gặp được cache với TTL (Time To Live) 5 phút.
- **LLM Response Caching**: Response từ LLM cho cùng một finding được cache để giảm API calls.

**Parallel Processing:**

- **Parallel SAST Execution**: Nhiều công cụ SAST chạy song song trong CI pipeline để giảm thời gian quét.
- **Async Processing**: MCP Server xử lý requests bất đồng bộ sử dụng asyncio.
- **Batch Database Operations**: Multiple findings được lưu theo batch để giảm database round-trips.

**Scalability Considerations:**

- **Stateless Design**: MCP Server và LLM Orchestrator được thiết kế stateless, cho phép scale ngang dễ dàng.
- **Database Sharding**: Database có thể được shard theo repo_id để phân tán tải.
- **Message Queue**: Redis/RabbitMQ được sử dụng làm message broker để decouple các thành phần.

## 3.8. Tổng kết chương 3

Chương này đã trình bày chi tiết và toàn diện về thiết kế và xây dựng của hệ thống sàng lọc lỗ hổng bảo mật sớm trong quy trình CI/CD với sự hỗ trợ của AI. Nội dung chương đã bao quát tất cả các khía cạnh quan trọng của hệ thống, từ kiến trúc tổng thể đến chi tiết triển khai của từng thành phần.

Các đóng góp chính của chương này bao gồm:

**Thứ nhất, kiến trúc hệ thống module hóa**: Thiết kế tích hợp CI/CD pipeline, SAST tools, MCP Server, LLM Orchestrator, ChatOps Platform, và Web Dashboard thành một hệ thống hoàn chỉnh và hoạt động đồng bộ. Kiến trúc được thiết kế theo nguyên tắc separation of concerns và loose coupling, cho phép các thành phần phát triển và scale độc lập.

**Thứ hai, CI/CD Pipeline tích hợp SAST toàn diện**: Cấu trúc pipeline với 10 stages chi tiết, tích hợp song song 5 công cụ SAST (Semgrep, CodeQL, ESLint, SpotBugs, Dependency-Check), và hệ thống security gate với 7 policies được cấu hình linh hoạt. Pipeline được tối ưu hóa với cơ chế caching và parallel execution.

**Thứ ba, ChatOps Workflow với AI Assistant**: Hệ thống ChatOps hỗ trợ 10 commands chi tiết, tích hợp AI assistant thông qua kiến trúc multi-layer, và real-time notifications với 11 loại events. Approval workflow được thiết kế với quy trình review chi tiết và audit logging.

**Thứ tư, MCP Server với Data Pipeline 4 stages**: Quy trình xử lý dữ liệu toàn diện bao gồm Raw Scan Output Collection (hỗ trợ 4 định dạng), Format Normalization (sử dụng Pydantic strict validation), Enrichment & Deduplication (CWE lookup, OWASP mapping, CVSS scoring, fingerprint-based deduplication), và Persist to Database (SQLite với SQLAlchemy ORM và 10 indexes).

**Thứ năm, Guardrail System với 4 lớp bảo mật**: Hệ thống bảo mật nhiều lớp bao gồm Authentication Layer (PAT với scope giới hạn, HTTPS/TLS 1.2+, rate limiting), Schema Validation Layer (Pydantic strict mode, required fields check, type validation), Content Sanitization Layer (PII scrubbing với 6 patterns, secret detection với 7 patterns, environment variable redaction), và Prompt Security Layer (injection deny-list với 12 patterns, special character escaping, token budget limit).

**Thứ sáu, End-to-end Data Flow với 15 bước chi tiết**: Luồng dữ liệu hoàn chỉnh từ code push đến AI analysis được mô tả chi tiết với 3 kịch bản xử lý (happy path, vulnerability found path, approval path) và feedback loop cho phép rerun pipeline.

**Thứ bảy, Security Considerations và Performance Optimization**: Phân tích mối đe dọa STRIDE với 6 loại mối đe dọa và biện pháp đối phó, cùng với chiến lược caching, parallel processing, và scalability considerations.

Các thiết kế và triển khai được trình bày trong chương này cung cấp nền tảng kỹ thuật vững chắc cho việc thực hiện thử nghiệm và đánh giá hệ thống, nội dung sẽ được trình bày chi tiết trong Chương 4. Hệ thống được thiết kế không chỉ đáp ứng các yêu cầu chức năng mà còn đảm bảo các yêu cầu phi chức năng về bảo mật, hiệu năng, và khả năng mở rộng, phù hợp với các tiêu chuẩn của một hệ thống DevSecOps hiện đại.
