import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Corpus explorer",
  description:
    "Read the quant-finance corpus and its compiled knowledge store: sources, concepts, contradictions, and the chains that reach a decision.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
