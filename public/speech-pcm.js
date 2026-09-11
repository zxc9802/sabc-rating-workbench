class SpeechPCM extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = [];
    this.phase = 0;
    this.sum = 0;
    this.count = 0;
    this.stopped = false;
    this.port.onmessage = () => {
      this.flush();
      this.stopped = true;
      this.port.postMessage('stopped');
    };
  }
  flush() {
    if (!this.samples.length) return;
    const buffer = new ArrayBuffer(this.samples.length * 2);
    const view = new DataView(buffer);
    this.samples.forEach((v, i) => view.setInt16(i * 2, v, true));
    this.port.postMessage(buffer, [buffer]);
    this.samples = [];
  }
  process(inputs) {
    if (this.stopped) return false;
    const input = inputs[0]?.[0];
    if (!input) return true;
    for (const value of input) {
      this.sum += value;
      this.count++;
      this.phase += 16000;
      if (this.phase >= sampleRate) {
        const v = Math.max(-1, Math.min(1, this.sum / this.count));
        this.samples.push(Math.round(v * (v < 0 ? 32768 : 32767)));
        this.phase -= sampleRate;
        this.sum = 0;
        this.count = 0;
        if (this.samples.length === 3200) this.flush();
      }
    }
    return true;
  }
}
registerProcessor('speech-pcm', SpeechPCM);
