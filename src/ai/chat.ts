import { generateText } from "ai";
import { env } from "../config/env.js";
import { getDefaultSelection, getProviderModel, type AiSelection } from "./provider.js";

export async function askAi(prompt: string, selection?: Partial<AiSelection>) {
  const defaults = getDefaultSelection();
  const provider = selection?.provider || defaults.provider;
  const model = selection?.model || defaults.model;
  const languageModel = getProviderModel(provider, model);

  const result = await generateText({
    model: languageModel,
    maxOutputTokens: env.MAX_OUTPUT_TOKENS,
    system: "أنت مساعد عربي عملي ودقيق. أجب بإيجاز مفيد، وإذا كان السؤال برمجيًا أعط خطوات أو كودًا واضحًا.",
    prompt
  });

  return {
    provider,
    model,
    text: result.text,
    usage: result.usage
  };
}
