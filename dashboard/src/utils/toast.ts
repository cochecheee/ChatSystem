import { toast } from 'sonner';

let _prevCritHigh = 0;

export const notify = {
  newFindings: (critHigh: number) => {
    if (critHigh > _prevCritHigh) {
      const diff = critHigh - _prevCritHigh;
      toast.warning(`${diff} Critical/High finding mới`, {
        description: 'Vào trang Vulnerabilities để xem chi tiết.',
        duration: 8000,
      });
    }
    _prevCritHigh = critHigh;
  },

  commandSuccess: (msg: string) => toast.success(msg),
  commandError:   (msg: string) => toast.error(msg),
  processing:     (msg: string) => toast.loading(msg, { id: 'processing' }),
  dismissProcessing: ()         => toast.dismiss('processing'),

  report: (onDownload: () => void) =>
    toast.success('Báo cáo đã sẵn sàng', {
      action: { label: 'Tải xuống', onClick: onDownload },
      duration: 10000,
    }),
};

export function updateCritHighBaseline(n: number) {
  _prevCritHigh = n;
}
