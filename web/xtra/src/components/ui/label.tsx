"use client";
import FormLabel, { type FormLabelProps } from "@mui/material/FormLabel";
import React from "react";
const Label = React.forwardRef<HTMLLabelElement, FormLabelProps>(
    (props, ref) => <FormLabel ref={ref} {...props} />,
);
Label.displayName = "Label";
export { Label };
