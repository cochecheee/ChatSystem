import { useEffect, useRef, useState } from 'react';
import { api, getAuthToken, setAuthToken } from '../api/client';
import { ApprovalDialog } from '../components/modals/ApprovalDialog';
import { RevokeDialog } from '../components/modals/RevokeDialog';
import { Icon } from '../components/Icon';
import { notify } from '../utils/toast';
import type { CommandResponse } from '../types';

interface Message {
  role: 'user' | 'ai' | 'system';
  text: string;
  loading?: boolean;
}

const PRESETS = ['/explain [id]', '/fix [id]', '/scan', '/approve [id]', '/revoke [id]', '/report', '/status'];

function parseCommand(input: string): { cmd: string; args: string[] } {
  const parts = input.trim().split(/\s+/);
  const cmd = parts[0].toLowerCase().replace(/^\//, '');
  const args = parts.slice(1);
  return { cmd, args };
}

function LoginOverlay({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('');
  const [role, setRole] = useState('developer');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async () => {
    if (!username.trim()) { setError('Nhập tên đăng nhập'); return; }
    setLoading(true);
    try {
      const res = await api.chat.login(username.trim(), role);
      setAuthToken(res.access_token);
      onLogin();
    } catch (e) {
      setError(String(e));
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'absolute', inset: 0, zIndex: 50,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(4px)',
    }}>
      <div style={{
        background: 'var(--surface-1)', border: '1px solid var(--line)',
        borderRadius: 12, padding: '28px 32px', width: 340,
        boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <div className="ai-orb" style={{ width: 28, height: 28 }} />
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Sentinel AI Login</div>
            <div className="muted" style={{ fontSize: 11.5 }}>Demo — chọn role để tiếp tục</div>
          </div>
        </div>

        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--fg-3)' }}>Username</label>
        <input
          style={{
            width: '100%', padding: '7px 10px', background: 'var(--surface-2)',
            border: '1px solid var(--line)', borderRadius: 6, color: 'var(--fg)',
            fontSize: 13, marginBottom: 12, outline: 'none',
          }}
          placeholder="alice"
          value={username}
          onChange={e => setUsername(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleLogin(); }}
        />

        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--fg-3)' }}>Role</label>
        <select
          style={{
            width: '100%', padding: '7px 10px', background: 'var(--surface-2)',
            border: '1px solid var(--line)', borderRadius: 6, color: 'var(--fg)',
            fontSize: 13, marginBottom: 16, outline: 'none',
          }}
          value={role}
          onChange={e => setRole(e.target.value)}
        >
          <option value="developer">developer</option>
          <option value="security_lead">security_lead</option>
          <option value="admin">admin</option>
        </select>

        {error && <div style={{ color: 'var(--sev-high-fg)', fontSize: 12, marginBottom: 12 }}>{error}</div>}

        <button className="btn primary" style={{ width: '100%' }} onClick={handleLogin} disabled={loading}>
          {loading ? 'Đang đăng nhập…' : 'Đăng nhập'}
        </button>
      </div>
    </div>
  );
}

export function PageChat() {
  const [messages, setMessages] = useState<Message[]>([{
    role: 'ai',
    text: 'Xin chào! Mình là Sentinel AI — trợ lý bảo mật của bạn. Dùng các lệnh bên dưới hoặc đặt câu hỏi bất kỳ.',
  }]);
  const [input, setInput] = useState('');
  const [authed, setAuthed] = useState(!!getAuthToken());
  const [approvalId, setApprovalId] = useState<number | null>(null);
  const [revokeId, setRevokeId] = useState<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const addMsg = (msg: Message) => setMessages(m => [...m, msg]);
  const replaceLastAi = (text: string) =>
    setMessages(m => m.map((msg, i) => i === m.length - 1 && msg.role === 'ai' ? { ...msg, text, loading: false } : msg));

  const handleReport = async () => {
    notify.processing('Đang tạo báo cáo…');
    try {
      const token = getAuthToken();
      const res = await fetch(api.chat.reportUrl(), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'security-report.html';
      a.click();
      URL.revokeObjectURL(url);
      notify.dismissProcessing();
      notify.report(() => {
        const a2 = document.createElement('a');
        a2.href = url;
        a2.download = 'security-report.html';
        a2.click();
      });
      addMsg({ role: 'ai', text: 'Báo cáo HTML đã được tải xuống thành công.' });
    } catch (e) {
      notify.dismissProcessing();
      notify.commandError(`Lỗi tạo báo cáo: ${e}`);
      addMsg({ role: 'ai', text: `Lỗi: ${e}` });
    }
  };

  const executeCommand = async (cmd: string, args: string[]) => {
    addMsg({ role: 'ai', text: '⏳ Đang xử lý…', loading: true });

    if (cmd === 'report') {
      setMessages(m => m.filter(msg => !(msg.loading)));
      await handleReport();
      return;
    }

    if (cmd === 'approve') {
      const id = parseInt(args[0]);
      if (isNaN(id)) { replaceLastAi('Cú pháp: /approve [finding_id]'); return; }
      setMessages(m => m.filter(msg => !(msg.loading)));
      setApprovalId(id);
      return;
    }

    if (cmd === 'revoke') {
      const id = parseInt(args[0]);
      if (isNaN(id)) { replaceLastAi('Cú pháp: /revoke [finding_id]'); return; }
      setMessages(m => m.filter(msg => !(msg.loading)));
      setRevokeId(id);
      return;
    }

    try {
      const req = {
        command: `/${cmd}`,
        finding_id: ['explain', 'fix'].includes(cmd) ? parseInt(args[0]) : undefined,
        run_id: cmd === 'rerun' ? parseInt(args[0]) : undefined,
      };

      const res: CommandResponse = await api.chat.command(req);
      notify.commandSuccess(res.message);

      let text = res.message;
      if (res.data?.explanation_vi) {
        text += `\n\n**Giải thích:** ${res.data.explanation_vi}`;
      }
      if (res.data?.impact_vi) {
        text += `\n\n**Tác động:** ${res.data.impact_vi}`;
      }
      if (res.data?.remediation_diff) {
        text += `\n\n**Remediation:**\n\`\`\`diff\n${res.data.remediation_diff}\n\`\`\``;
      }
      replaceLastAi(text);
    } catch (e) {
      const msg = String(e);
      notify.commandError(msg);
      replaceLastAi(`Lỗi: ${msg}`);
    }
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text) return;
    addMsg({ role: 'user', text });
    setInput('');

    if (text.startsWith('/')) {
      const { cmd, args } = parseCommand(text);
      await executeCommand(cmd, args);
    } else {
      addMsg({ role: 'ai', text: 'Để phân tích một finding cụ thể, dùng /explain [id]. Để xem danh sách, vào trang Vulnerabilities.' });
    }
  };

  const handleApproveConfirm = async (justification: string) => {
    if (approvalId === null) return;
    const res = await api.chat.command({ command: '/approve', finding_id: approvalId, justification });
    notify.commandSuccess(res.message);
    addMsg({ role: 'ai', text: res.message });
    setApprovalId(null);
  };

  const handleRevokeConfirm = async (justification: string) => {
    if (revokeId === null) return;
    const res = await api.chat.command({ command: '/revoke', finding_id: revokeId, justification });
    notify.commandSuccess(res.message);
    addMsg({ role: 'ai', text: res.message });
    setRevokeId(null);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 52px)', position: 'relative' }}>
      {!authed && <LoginOverlay onLogin={() => setAuthed(true)} />}

      <div style={{ padding: '20px 28px 0', borderBottom: '1px solid var(--line)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div className="ai-orb" />
            <div>
              <h1 className="h2">AI Assistant</h1>
              <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>Sentinel AI · Gemini · tiếng Việt</div>
            </div>
          </div>
          {authed && (
            <button className="btn ghost sm" onClick={() => { setAuthToken(null); setAuthed(false); }}>
              Đăng xuất
            </button>
          )}
        </div>
      </div>

      <div className="ai-messages" style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-role">
              <Icon name={m.role === 'user' ? 'user' : 'bot'} size={13} />
              <span className="who">{m.role === 'user' ? 'Bạn' : 'Sentinel AI'}</span>
            </div>
            <div className="msg-body">
              {m.loading
                ? <span className="muted">⏳ Đang xử lý…</span>
                : m.text.split('\n').map((line, j) => <p key={j}>{line}</p>)
              }
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div style={{ padding: '0 28px 8px', display: 'flex', gap: 6, flexWrap: 'wrap', flexShrink: 0 }}>
        {PRESETS.map(cmd => (
          <span key={cmd} className="suggestion-chip"
            onClick={() => { setInput(cmd.replace(' [id]', ' ')); textareaRef.current?.focus(); }}>
            {cmd}
          </span>
        ))}
      </div>

      <div className="ai-composer" style={{ padding: '0 28px 20px', flexShrink: 0 }}>
        <div className="ai-composer-box">
          <textarea
            ref={textareaRef}
            data-testid="chat-input"
            rows={3}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
            placeholder="Đặt câu hỏi hoặc nhập lệnh /explain 1, /fix 1, /scan… (Enter để gửi)"
          />
          <div className="ai-composer-row">
            <span className="grow" />
            <button className="btn primary" onClick={sendMessage} disabled={!input.trim()}>
              <Icon name="send" size={13} /> Gửi
            </button>
          </div>
        </div>
      </div>

      <ApprovalDialog
        open={approvalId !== null}
        findingId={approvalId ?? 0}
        onClose={() => setApprovalId(null)}
        onConfirm={handleApproveConfirm}
      />
      <RevokeDialog
        open={revokeId !== null}
        findingId={revokeId ?? 0}
        onClose={() => setRevokeId(null)}
        onConfirm={handleRevokeConfirm}
      />
    </div>
  );
}
