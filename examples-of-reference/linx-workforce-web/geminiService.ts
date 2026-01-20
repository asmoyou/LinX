
import { GoogleGenAI, Type, GenerateContentResponse } from "@google/genai";

const getAI = () => new GoogleGenAI({ apiKey: process.env.API_KEY || '' });

export const geminiService = {
  // Requirement 1: Goal Decomposition with Language Support
  async decomposeGoal(goalDescription: string, lang: 'zh' | 'en' = 'zh'): Promise<any[]> {
    const ai = getAI();
    const systemInstruction = lang === 'zh' 
      ? '请使用中文返回任务分解结果。' 
      : 'Please return the task decomposition results in English.';

    const response = await ai.models.generateContent({
      model: 'gemini-3-pro-preview',
      contents: `Decompose the following business goal into a hierarchical JSON structure of tasks. 
                 Language context: ${lang}. ${systemInstruction}
                 Goal: "${goalDescription}"
                 Return an array of objects: { goal: string, assignedToType: string, estimatedComplexity: number }.`,
      config: {
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              goal: { type: Type.STRING },
              assignedToType: { type: Type.STRING },
              estimatedComplexity: { type: Type.NUMBER }
            },
            required: ['goal', 'assignedToType']
          }
        }
      }
    });

    try {
      return JSON.parse(response.text || '[]');
    } catch (e) {
      console.error("Failed to parse decomposition result", e);
      return [];
    }
  },

  // Requirement: Use Google Search Grounding
  async searchInformation(query: string) {
    const ai = getAI();
    const response = await ai.models.generateContent({
      model: "gemini-3-flash-preview",
      contents: query,
      config: {
        tools: [{ googleSearch: {} }],
      },
    });
    
    return {
      text: response.text,
      sources: response.candidates?.[0]?.groundingMetadata?.groundingChunks || []
    };
  },

  // Requirement: Generate Images with size selection
  async generateImage(prompt: string, size: "1K" | "2K" | "4K" = "1K") {
    const ai = getAI();
    const response = await ai.models.generateContent({
      model: 'gemini-3-pro-image-preview',
      contents: {
        parts: [{ text: prompt }]
      },
      config: {
        imageConfig: {
          aspectRatio: "1:1",
          imageSize: size
        }
      }
    });

    for (const part of response.candidates?.[0]?.content.parts || []) {
      if (part.inlineData) {
        return `data:image/png;base64,${part.inlineData.data}`;
      }
    }
    return null;
  }
};
