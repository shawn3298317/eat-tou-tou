import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Taipei Eats 台北口袋名單",
  description: "Taipei restaurant recommendations, ranked from community replies.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
