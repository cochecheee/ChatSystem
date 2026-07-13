import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import { Icon } from '../../components/Icon';
import { useActiveProjectParam } from '../../contexts/ProjectContext';
import { POLL_INTERVAL_MS } from '../../lib/constants';
import type { WorkflowJob, WorkflowJobStep, WorkflowRun } from '../../types';
import { LogViewer } from './LogViewer';

// CI Progress — jobs + steps của 1 run, poll live khi run đang chạy.
// GitHub cập nhật step status real-time qua /runs/{id}/jobs; log thì chỉ
// phát hành sau khi job kết thúc → job đang chạy hiển thị steps thay log.

function StatusIcon({ status, conclusion }: { status: string; conclusion: string | null }) {
  if (status === 'in_progress') {
    return (
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: 'var(--accent)',
          animation: 'pulse 1.5s ease-in-out infinite',
          flexShrink: 0,
        }}
      />
    );
  }
  if (status !== 'completed') {
    // queued / waiting / pending
    return (
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          border: '1.5px solid var(--fg-4)',
          flexShrink: 0,
        }}
      />
    );
  }
  if (conclusion === 'success') {
    return (
      <Icon name="check" size={12} style={{ color: 'var(--sev-low-fg, #43a047)', flexShrink: 0 }} />
    );
  }
  if (conclusion === 'failure') {
    return (
      <Icon name="x" size={12} style={{ color: 'var(--sev-crit-fg, #e53935)', flexShrink: 0 }} />
    );
  }
  // skipped / cancelled / neutral
  return <span style={{ color: 'var(--fg-4)', fontSize: 11, flexShrink: 0 }}>—</span>;
}

function duration(started?: string | null, completed?: string | null): string {
  if (!started) return '';
  const end = completed ? new Date(completed).getTime() : Date.now();
  const s = Math.max(0, Math.floor((end - new Date(started).getTime()) / 1000));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}m ${s % 60}s` : `${s}s`;
}

function StepRow({ step }: { step: WorkflowJobStep }) {
  const dim = step.status === 'completed' && step.conclusion === 'skipped';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '3px 0' }}>
      <StatusIcon status={step.status} conclusion={step.conclusion} />
      <span
        style={{
          fontSize: 11.5,
          color: dim ? 'var(--fg-4)' : 'var(--fg-2)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {step.name}
      </span>
      <span className="mono muted" style={{ fontSize: 10, marginLeft: 'auto', flexShrink: 0 }}>
        {duration(step.started_at, step.completed_at)}
      </span>
    </div>
  );
}

function JobCard({
  job,
  runId,
  projectId,
}: {
  job: WorkflowJob;
  runId: number;
  projectId?: number;
}) {
  // Job fail hoặc đang chạy mở sẵn steps — đó là nơi cần nhìn.
  const [open, setOpen] = useState(job.status !== 'completed' || job.conclusion === 'failure');
  const [showLog, setShowLog] = useState(false);

  const done = job.steps.filter((s) => s.status === 'completed').length;
  const logReady = job.status === 'completed';

  return (
    <div style={{ borderTop: '1px solid var(--line)', padding: '8px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div
          onClick={() => setOpen(!open)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            cursor: 'pointer',
            flex: 1,
            minWidth: 0,
          }}
        >
          <Icon
            name={open ? 'chevron_down' : 'chevron_right'}
            size={10}
            style={{ color: 'var(--fg-3)' }}
          />
          <StatusIcon status={job.status} conclusion={job.conclusion} />
          <span
            style={{
              fontSize: 12.5,
              fontWeight: 600,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {job.name}
          </span>
          <span className="muted" style={{ fontSize: 10.5, flexShrink: 0 }}>
            {job.status === 'in_progress' ? `${done}/${job.steps.length} steps` : ''}
          </span>
        </div>
        <span className="mono muted" style={{ fontSize: 10.5, flexShrink: 0 }}>
          {duration(job.started_at, job.completed_at)}
        </span>
        {logReady ? (
          <button className="btn ghost sm" onClick={() => setShowLog(!showLog)}>
            <Icon name="play" size={11} /> {showLog ? 'Hide log' : 'View log'}
          </button>
        ) : (
          <span className="muted" style={{ fontSize: 10, flexShrink: 0 }}>
            log after finish
          </span>
        )}
      </div>
      {open && job.steps.length > 0 && (
        <div
          style={{ margin: '6px 0 0 26px', paddingLeft: 10, borderLeft: '1px solid var(--line)' }}
        >
          {job.steps.map((s) => (
            <StepRow key={s.number} step={s} />
          ))}
        </div>
      )}
      {showLog && logReady && <LogViewer runId={runId} jobId={job.id} projectId={projectId} />}
    </div>
  );
}

export function JobsPanel({ run }: { run: WorkflowRun }) {
  const { project_id } = useActiveProjectParam();
  const [jobs, setJobs] = useState<WorkflowJob[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.github
      .runJobs(run.id, project_id)
      .then((arr) => {
        setJobs(arr);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, [run.id, project_id]);

  useEffect(() => {
    // Reset qua callback của load() — không set state trực tiếp trong effect
    // (react-hooks/set-state-in-effect). Poll chỉ khi run chưa completed;
    // parent (Pipelines) tự cập nhật run.status nên effect re-run và dừng
    // interval + fetch trạng thái chốt khi run xong.
    load();
    if (run.status === 'completed') return;
    const id = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [load, run.status]);

  const live = run.status !== 'completed';

  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <div className="card-header">
        <div className="h3" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          CI Progress
          {live && (
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: 'var(--accent)',
                animation: 'pulse 1.5s ease-in-out infinite',
              }}
            />
          )}
        </div>
        <span className="muted" style={{ fontSize: 11 }}>
          {jobs === null
            ? '…'
            : `${jobs.filter((j) => j.status === 'completed').length}/${jobs.length} jobs done`}
        </span>
      </div>
      <div style={{ padding: '0 14px 8px' }}>
        {error && (
          <div
            className="muted"
            style={{ fontSize: 11, padding: '10px 0', color: 'var(--err-fg)' }}
          >
            {error}
          </div>
        )}
        {!error && jobs === null && (
          <div className="muted" style={{ fontSize: 11, padding: '10px 0' }}>
            Loading jobs…
          </div>
        )}
        {!error && jobs !== null && jobs.length === 0 && (
          <div className="muted" style={{ fontSize: 11, padding: '10px 0' }}>
            {live ? 'Waiting for runner…' : 'No jobs reported for this run'}
          </div>
        )}
        {!error &&
          jobs !== null &&
          jobs.map((j) => <JobCard key={j.id} job={j} runId={run.id} projectId={project_id} />)}
      </div>
    </div>
  );
}
