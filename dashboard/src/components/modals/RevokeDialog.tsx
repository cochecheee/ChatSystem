import { ActionDialog } from './ActionDialog';

interface Props {
  open: boolean;
  findingId: number;
  onClose: () => void;
  onConfirm: (justification: string) => Promise<void>;
}

export function RevokeDialog({ open, findingId, onClose, onConfirm }: Props) {
  return (
    <ActionDialog
      open={open}
      onClose={onClose}
      onConfirm={onConfirm}
      title="Thu hồi phê duyệt"
      description="Đánh dấu finding này cần xem xét lại. Hành động này sẽ được ghi vào audit trail và không thể hoàn tác."
      confirmLabel="Thu hồi"
      confirmDanger={true}
      findingId={findingId}
    />
  );
}
