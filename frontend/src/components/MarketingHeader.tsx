"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Dna, Menu, X } from "lucide-react";

const LINKS = [
  { href: "#product", label: "Product" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#security", label: "Security" },
  { href: "#faq", label: "FAQ" },
];

export default function MarketingHeader() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-50 bg-white transition-shadow ${
        scrolled ? "mkt-glass" : "border-b border-transparent"
      }`}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4 lg:px-8">
        <Link href="/" className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-xl border border-crimson/25 bg-crimson/10">
            <Dna className="size-5 text-crimson" />
          </span>
          <span>
            <span className="block text-sm font-bold tracking-[0.22em] text-navy-950">
              GENOGUIDE
            </span>
            <span className="block text-[10px] uppercase tracking-widest text-navy-800">
              Genomic Intelligence
            </span>
          </span>
        </Link>

        <nav className="hidden items-center gap-8 md:flex">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="text-sm text-navy-800 transition-colors hover:text-navy-950"
            >
              {l.label}
            </a>
          ))}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <Link
            href="/login"
            className="text-sm font-medium text-navy-800 transition-colors hover:text-navy-950"
          >
            Sign in
          </Link>
          <Link
            href="/signup"
            className="group inline-flex items-center gap-2 rounded-xl bg-crimson px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-maroon"
          >
            Sign up
            <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-1" />
          </Link>
        </div>

        <button
          onClick={() => setOpen((v) => !v)}
          className="grid size-9 place-items-center rounded-lg border border-navy-800/15 text-navy-800 md:hidden"
          aria-label="Toggle menu"
        >
          {open ? <X className="size-4" /> : <Menu className="size-4" />}
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.nav
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden border-t border-navy-800/10 bg-white md:hidden"
          >
            <div className="flex flex-col gap-1 px-6 py-4">
              {LINKS.map((l) => (
                <a
                  key={l.href}
                  href={l.href}
                  onClick={() => setOpen(false)}
                  className="rounded-lg px-3 py-2.5 text-sm text-navy-800 hover:bg-navy-950/5 hover:text-navy-950"
                >
                  {l.label}
                </a>
              ))}
              <Link
                href="/login"
                onClick={() => setOpen(false)}
                className="mt-2 rounded-lg px-3 py-2.5 text-center text-sm font-medium text-navy-800 hover:bg-navy-950/5 hover:text-navy-950"
              >
                Sign in
              </Link>
              <Link
                href="/signup"
                onClick={() => setOpen(false)}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-crimson px-4 py-2.5 text-sm font-semibold text-white"
              >
                Sign up
                <ArrowRight className="size-3.5" />
              </Link>
            </div>
          </motion.nav>
        )}
      </AnimatePresence>
    </header>
  );
}
