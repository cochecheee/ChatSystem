import { ActionDialog } from './ActionDialog';

interface Props {
  open: boolean;
  findingId: number;
  onClose: () => void;
  onConfirm: (justification: string) => Promise<void>;
}

export function ApprovalDialog({ open, findingId, onClose, onConfirm }: Props) {
  return (
    <ActionDialog
      open={open}
      onClose={onClose}
      onConfirm={onConfirm}
      title="Phê duyệt Finding"
      description="Xác nhận finding này là false positive hoặc đã được xử lý. Hành động này sẽ được ghi vào audit trail."
      confirmLabel="Xác nhận phê duyệt"
      confirmDanger={false}
      findingId={findingId}
    />
  );
}
