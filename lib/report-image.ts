import html2canvas from 'html2canvas-pro';

export async function exportReportImage(report: HTMLElement, filename: string) {
  const container = document.createElement('div');
  container.setAttribute('aria-hidden', 'true');
  container.style.cssText = 'position:absolute;left:-10000px;top:0;width:1080px;pointer-events:none';
  container.append(report);
  document.body.append(container);
  try {
    await document.fonts.ready;
    const options = {
      backgroundColor: '#2d3842',
      scale: 2,
      windowWidth: 1440,
      logging: false,
      onclone: (_document: Document, imageReport: HTMLElement) => {
        imageReport.style.cssText = 'width:1080px;max-width:none;margin:0;background:#2d3842;box-shadow:none;backdrop-filter:none';
        imageReport.querySelectorAll('details').forEach(item => { item.open = true; });
        imageReport.querySelectorAll<HTMLElement>('pre').forEach(item => {
          item.style.maxHeight = 'none';
          item.style.overflow = 'visible';
        });
        const { width, height } = imageReport.getBoundingClientRect();
        // Keep long reports within canvas dimension and memory limits.
        options.scale = Math.min(2, 16384 / height, Math.sqrt(16000000 / (width * height)));
      },
    };
    const canvas = await html2canvas(report, options);
    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(value => value ? resolve(value) : reject(new Error('长图生成失败，请重试。')), 'image/png');
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_') + '.png';
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 60000);
  } finally {
    container.remove();
  }
}
