// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import type { ReactNode } from "react";

interface PanelSectionProps {
  label: string;
  children?: ReactNode;
  loading?: boolean;
  loadingText?: string;
}

export function PanelSection({ label, children, loading, loadingText = "Loading..." }: PanelSectionProps) {
  return (
    <div className="panel-section">
      <p className="panel-label">{label}</p>
      {loading ? (
        <p style={{ fontSize: "11px", color: "var(--text-muted)" }}>{loadingText}</p>
      ) : (
        children
      )}
    </div>
  );
}
