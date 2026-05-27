/**
 * UI-примитивы дизайн-системы Reelibra (брендбук «латунь на чёрном лаке»).
 * Чистая презентация, токены через var(--*), прямые углы, a11y, тач ≥44px.
 */
import "./ui-primitives.css";

export { cn } from "./cn";
export type { ClassValue } from "./cn";

export { Button } from "./Button";
export type { ButtonProps, ButtonVariant, ButtonSize } from "./Button";

export { Card } from "./Card";
export type { CardProps } from "./Card";

export { Field } from "./Field";
export type { FieldProps } from "./Field";

export { Input, Textarea } from "./Input";
export type { InputProps, TextareaProps } from "./Input";

export { Select } from "./Select";
export type { SelectProps, SelectOption } from "./Select";

export { Switch } from "./Switch";
export type { SwitchProps } from "./Switch";

export { Slider } from "./Slider";
export type { SliderProps } from "./Slider";

export { Modal } from "./Modal";
export type { ModalProps, ModalSize } from "./Modal";

export { Tooltip } from "./Tooltip";
export type { TooltipProps, TooltipSide } from "./Tooltip";

export { Toast, ToastViewport } from "./Toast";
export type { ToastProps, ToastViewportProps, ToastData, ToastType } from "./Toast";

export { ConfirmDialog } from "./ConfirmDialog";
export type { ConfirmDialogProps } from "./ConfirmDialog";

export { ErrorBoundary } from "./ErrorBoundary";
export type { ErrorBoundaryProps } from "./ErrorBoundary";

export { Skeleton, SkeletonReelGrid, SkeletonRow } from "./Skeleton";
export type { SkeletonProps, SkeletonGridProps } from "./Skeleton";

export { Badge, HONESTY_LABELS } from "./Badge";
export type { BadgeProps, BadgeVariant, HonestyBadge, StatusBadge } from "./Badge";
