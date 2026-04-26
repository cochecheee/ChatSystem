import { useRef, useState } from 'react';
import { Icon } from '../components/Icon';

interface Message { role: 'user' | 'ai'; text: string }

const PRESETS = ['/explain', '/fix', '/scan', '/results', '/status', '/report'];

export function PageChat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'ai',
      text: 'Xin chào! Mình là Sentinel AI — trợ lý bảo mật của bạn. Mình có thể giúp bạn phân tích lỗ hổng, đề xuất cách fix, hoặc giải thích các kết quả SAST. Hãy chọn một lệnh hoặc đặt câu hỏi bất kỳ.',
    },
  ]);
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const sendMessage = () => {
    const text = input.trim();
    if (!text) return;
    setMessages(m => [...m, { role: 'user', text }]);
    setInput('');
    setTimeout(() => {
      setMessages(m => [...m, {
        role: 'ai',
        text: text.startsWith('/')
          ? `Lệnh ${text} sẽ được hỗ trợ đầy đủ trong Phase 6. Hiện tại, bạn có thể dùng trang Vulnerabilities để phân tích từng finding bằng AI.`
          : 'Để phân tích một finding cụ thể, hãy vào trang Vulnerabilities, chọn finding và nhấn "Phân tích AI".',
      }]);
    }, 800);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 52px)' }}>
      <div style={{ padding: '20px 28px 0', borderBottom: '1px solid var(--line)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 16 }}>
          <div className="ai-orb" />
          <div>
            <h1 className="h2">AI Assistant</h1>
            <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>Sentinel AI · powered by Gemini · tiếng Việt</div>
          </div>
        </div>
      </div>

      <div className="ai-messages" style={{ flex: 1 }}>
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-role">
              <Icon name={m.role === 'user' ? 'user' : 'bot'} size={13} />
              <span className="who">{m.role === 'user' ? 'Bạn' : 'Sentinel AI'}</span>
            </div>
            <div className="msg-body"><p>{m.text}</p></div>
          </div>
        ))}
      </div>

      <div style={{ padding: '0 28px 8px', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {PRESETS.map(cmd => (
          <span key={cmd} className="suggestion-chip" onClick={() => setInput(cmd)}>{cmd}</span>
        ))}
      </div>

      <div className="ai-composer" style={{ padding: '0 28px 20px' }}>
        <div className="ai-composer-box">
          <textarea
            ref={textareaRef}
            rows={3}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
            placeholder="Đặt câu hỏi hoặc nhập lệnh /explain, /fix, /scan… (Enter để gửi)"
          />
          <div className="ai-composer-row">
            <span className="grow" />
            <button className="btn primary" onClick={sendMessage} disabled={!input.trim()}>
              <Icon name="send" size={13} /> Gửi
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
