import "./globals.css";

export const metadata = {
  title: "coderag",
  description: "ask questions about any github repo",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
