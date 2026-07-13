import { useEffect, useRef, useState } from 'react';
import { api, getAuthToken } from '../api/client';
import { useAuth } from '../features/auth/AuthContext';
import { AlertBanner } from '../components/AlertBanner';
import { ApprovalDialog } from '../components/modals/ApprovalDialog';
import { RevokeDialog } from '../components/modals/RevokeDialog';
import { Icon } from '../components/Icon';
import { InvestigationCard } from '../features/findings/InvestigationCard';
import type { CommandResponse, FPInvestigation } from '../types';

interface Message {
  role: 'user' | 'ai' | 'system';
  text: string;
  loading?: boolean;
  suggestedCommand?: string | null;
  investigation?: FPInvestigation | null;
}

const PRESETS = [
  '/explain [id]',
  '/verify [id]',
  '/fix [id]',
  '/scan',
  '/approve [id]',
  '/revoke [id]',
  '/report',
];

function parseCommand(input: string): { cmd: string; args: string[] } {
  const parts = input.trim().split(/\s+/);
  const cmd = parts[0].toLowerCase().replace(/^\//, '');
  const args = parts.slice(1);
  return { cmd, args };
}

export function PageChat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'ai',
      text: 'Xin chào! Mình là Shiftwall AI — trợ lý bảo mật của bạn. Bạn có thể chat tự do bằng tiếng Việt, hoặc dùng lệnh nhanh như /explain 5, /scan, /report.',
    },
  ]);
  const { user, loading: authLoading, logout } = useAuth();
  const authed = !!user;
  const [input, setInput] = useState('');
  const [approvalId, setApprovalId] = useState<number | null>(null);
  const [revokeId, setRevokeId] = useState<number | null>(null);
  const [cmdStatus, setCmdStatus] = useState<{ type: 'success' | 'error'; msg: string } | null>(
    null
  );
  const [reportStatus, setReportStatus] = useState<{
    type: 'success' | 'error';
    msg: string;
    downloadUrl?: string;
  } | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const addMsg = (msg: Message) => setMessages((m) => [...m, msg]);
  const replaceLastAi = (text: string) =>
    setMessages((m) =>
      m.map((msg, i) =>
        i === m.length - 1 && msg.role === 'ai' ? { ...msg, text, loading: false } : msg
      )
    );

  const handleReport = async () => {
    setReportLoading(true);
    setReportStatus(null);
    try {
      const token = getAuthToken();
      const res = await fetch(api.chat.reportUrl(), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setReportLoading(false);
      setReportStatus({ type: 'success', msg: 'Báo cáo đã sẵn sàng', downloadUrl: url });
    } catch (e) {
      setReportLoading(false);
      setReportStatus({ type: 'error', msg: `Lỗi tạo báo cáo: ${e}` });
    }
  };

  const executeCommand = async (cmd: string, args: string[]) => {
    addMsg({ role: 'ai', text: '⏳ Đang xử lý…', loading: true });

    if (cmd === 'report') {
      setMessages((m) => m.filter((msg) => !msg.loading));
      await handleReport();
      return;
    }

    if (cmd === 'approve') {
      const id = parseInt(args[0]);
      if (isNaN(id)) {
        replaceLastAi('Cú pháp: /approve [finding_id]');
        return;
      }
      setMessages((m) => m.filter((msg) => !msg.loading));
      setApprovalId(id);
      return;
    }

    if (cmd === 'revoke') {
      const id = parseInt(args[0]);
      if (isNaN(id)) {
        replaceLastAi('Cú pháp: /revoke [finding_id]');
        return;
      }
      setMessages((m) => m.filter((msg) => !msg.loading));
      setRevokeId(id);
      return;
    }

    try {
      const req = {
        command: `/${cmd}`,
        finding_id: ['explain', 'fix', 'verify'].includes(cmd) ? parseInt(args[0]) : undefined,
        run_id: cmd === 'rerun' ? parseInt(args[0]) : undefined,
      };

      const res: CommandResponse = await api.chat.command(req);

      // V4.3 — /verify returns an FPInvestigation payload → render as a card.
      if (cmd === 'verify' && res.data && 'verdict' in res.data) {
        const inv = res.data as unknown as FPInvestigation;
        setMessages((m) =>
          m.map((msg, i) =>
            i === m.length - 1 && msg.role === 'ai'
              ? {
                  ...msg,
                  text: inv.summary_vi || res.message,
                  loading: false,
                  investigation: inv,
                  suggestedCommand: inv.suggested_command ?? null,
                }
              : msg
          )
        );
        setCmdStatus({ type: 'success', msg: res.message });
        return;
      }

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
      setCmdStatus({ type: 'success', msg: res.message });
    } catch (e) {
      const msg = String(e);
      replaceLastAi(`Lỗi: ${msg}`);
      setCmdStatus({ type: 'error', msg });
    }
  };

  const sendNaturalLanguage = async (text: string) => {
    addMsg({ role: 'ai', text: '⏳ Đang xử lý…', loading: true });
    try {
      const res = await api.chat.message(text);
      setMessages((m) =>
        m.map((msg, i) =>
          i === m.length - 1 && msg.role === 'ai'
            ? {
                ...msg,
                text: res.reply,
                loading: false,
                suggestedCommand: res.suggested_command,
                investigation: res.investigation ?? null,
              }
            : msg
        )
      );
    } catch (e) {
      replaceLastAi(`Lỗi: ${e}`);
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
      await sendNaturalLanguage(text);
    }
  };

  const handleSuggestedCommand = async (cmdText: string) => {
    setInput('');
    addMsg({ role: 'user', text: cmdText });
    const { cmd, args } = parseCommand(cmdText);
    await executeCommand(cmd, args);
  };

  const handleApproveConfirm = async (justification: string) => {
    if (approvalId === null) return;
    try {
      const res = await api.chat.command({
        command: '/approve',
        finding_id: approvalId,
        justification,
      });
      setCmdStatus({ type: 'success', msg: res.message });
    } catch (e) {
      setCmdStatus({ type: 'error', msg: String(e) });
    }
    setApprovalId(null);
  };

  const handleRevokeConfirm = async (justification: string) => {
    if (revokeId === null) return;
    try {
      const res = await api.chat.command({
        command: '/revoke',
        finding_id: revokeId,
        justification,
      });
      setCmdStatus({ type: 'success', msg: res.message });
    } catch (e) {
      setCmdStatus({ type: 'error', msg: String(e) });
    }
    setRevokeId(null);
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: 'calc(100vh - 52px)',
        position: 'relative',
      }}
    >
      {!authLoading && !authed && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 5,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(0,0,0,0.4)',
            backdropFilter: 'blur(2px)',
            fontSize: 13,
            color: 'var(--fg-2)',
            textAlign: 'center',
            padding: 24,
          }}
        >
          Đăng nhập qua nút <strong>Sign in</strong> ở góc phải topbar để dùng AI Chat.
        </div>
      )}

      <div style={{ padding: '20px 28px 0', borderBottom: '1px solid var(--line)', flexShrink: 0 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingBottom: 16,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div className="ai-orb" />
            <div>
              <h1 className="h2">AI Assistant</h1>
              <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>
                Shiftwall AI · Gemini · tiếng Việt
              </div>
            </div>
          </div>
          {authed && (
            <button className="btn ghost sm" onClick={logout}>
              Đăng xuất {user ? `(${user.username})` : ''}
            </button>
          )}
        </div>
      </div>

      {cmdStatus && (
        <AlertBanner
          type={cmdStatus.type}
          message={cmdStatus.msg}
          onDismiss={() => setCmdStatus(null)}
        />
      )}
      {reportStatus && (
        <AlertBanner
          type={reportStatus.type}
          message={reportStatus.msg}
          onDismiss={() => setReportStatus(null)}
          action={
            reportStatus.downloadUrl
              ? {
                  label: 'Tải xuống',
                  onClick: () => {
                    const a = document.createElement('a');
                    a.href = reportStatus.downloadUrl!;
                    a.download = '';
                    a.click();
                  },
                }
              : undefined
          }
        />
      )}
      {reportLoading && <AlertBanner type="info" message="Đang tạo báo cáo…" />}

      <div className="ai-messages" style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-role">
              <Icon name={m.role === 'user' ? 'user' : 'bot'} size={13} />
              <span className="who">{m.role === 'user' ? 'Bạn' : 'Shiftwall AI'}</span>
            </div>
            <div className="msg-body">
              {m.loading ? (
                <span className="muted">⏳ Đang xử lý…</span>
              ) : (
                m.text.split('\n').map((line, j) => <p key={j}>{line}</p>)
              )}
            </div>
            {m.investigation && !m.loading && <InvestigationCard inv={m.investigation} />}
            {m.suggestedCommand && !m.loading && (
              <div className="msg-actions" style={{ marginTop: 6 }}>
                <span
                  className="suggestion-chip"
                  onClick={() => handleSuggestedCommand(m.suggestedCommand!)}
                  style={{ cursor: 'pointer' }}
                >
                  <Icon name="sparkle" size={11} style={{ marginRight: 4 }} />
                  Chạy {m.suggestedCommand}
                </span>
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div
        style={{ padding: '0 28px 8px', display: 'flex', gap: 6, flexWrap: 'wrap', flexShrink: 0 }}
      >
        {PRESETS.map((cmd) => (
          <span
            key={cmd}
            className="suggestion-chip"
            onClick={() => {
              setInput(cmd.replace(' [id]', ' '));
              textareaRef.current?.focus();
            }}
          >
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
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            placeholder="Hỏi tự do bằng tiếng Việt, hoặc gõ lệnh /explain 1, /fix 1, /scan… (Enter để gửi)"
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
