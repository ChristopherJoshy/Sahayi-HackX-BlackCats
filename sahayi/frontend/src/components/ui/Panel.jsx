import { forwardRef } from "react";

/**
 * Panel card with an optional titled header.
 * @param {{ title?: string, eyebrow?: string, icon?: object, action?: object, className?: string, bodyClassName?: string, children: object }} props
 */
const Panel = forwardRef(function Panel(
  { title, eyebrow, icon: Icon, action, className = '', bodyClassName = '', children },
  ref
) {
  return (
    <section ref={ref} className={`panel ${className}`}>
      {(title || eyebrow || action) && (
        <div className="panel-head">
          <div className="flex items-center gap-2.5 min-w-0">
            {Icon && (
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                <Icon size={15} />
              </span>
            )}
            <div className="min-w-0">
              {eyebrow && <p className="eyebrow leading-none">{eyebrow}</p>}
              {title && (
                <h2 className="truncate text-sm font-semibold text-ink leading-tight">
                  {title}
                </h2>
              )}
            </div>
          </div>
          {action}
        </div>
      )}
      <div className={bodyClassName || 'p-5'}>{children}</div>
    </section>
  );
});

export default Panel;
