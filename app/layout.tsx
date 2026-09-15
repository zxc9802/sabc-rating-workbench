import type { Metadata } from 'next';
import '@fontsource-variable/noto-sans-sc';
import './globals.css';
import './glass.css';

export const metadata: Metadata = { title: 'SABC · 项目评级工作台', description: '结合公司现状与证据，判断项目现在是否值得投入。' };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
