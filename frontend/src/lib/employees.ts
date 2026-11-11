// Same rule as NIC_PATTERN in backend/app/schemas/hr.py: the old 9 digits
// plus V or X, or the 12-digit number issued since 2016.
export const NIC_PATTERN = /^(\d{9}[VX]|\d{12})$/;

export const NIC_RULE = 'NIC must be 9 digits followed by V or X, or 12 digits';
