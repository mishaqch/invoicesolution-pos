import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { cn } from "@/lib/cn";
/** A page section with consistent vertical rhythm + container. */
export function Section({ children, className, containerClassName, id, }) {
    return (_jsx("section", { id: id, className: cn("section", className), children: _jsx("div", { className: cn("container", containerClassName), children: children }) }));
}
/** Centered eyebrow + heading + optional lead, reused at the top of sections. */
export function SectionHeading({ eyebrow, title, lead, center = true, className, }) {
    return (_jsxs("div", { className: cn(center && "mx-auto max-w-2xl text-center", "mb-12", className), children: [eyebrow && _jsx("span", { className: "eyebrow mb-4", children: eyebrow }), _jsx("h2", { className: "h2", children: title }), lead && _jsx("p", { className: "lead mt-4", children: lead })] }));
}
