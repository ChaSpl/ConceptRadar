import google.genai.models

def apply_patches():
    """
    Applies global monkeypatches to genai.Client and Models/AsyncModels to robustly
    handle transient 429 errors and quota limits via automatic model fallbacks.
    """
    try:
        if getattr(apply_patches, "_applied", False):
            return
        apply_patches._applied = True
        
        # 1. Monkeypatch Models.generate_content for automatic model fallbacks (Sync)
        original_generate_content = google.genai.models.Models.generate_content

        def patched_generate_content(self, *args, **kwargs):
            model = kwargs.get("model")
            if not model and len(args) > 0:
                model = args[0]
                
            # Fallback list for standard flash models
            fallback_models = []
            is_flash = False
            if model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]:
                is_flash = True
                if model == "gemini-2.5-flash":
                    fallback_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]
                elif model == "gemini-2.0-flash":
                    fallback_models = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
                else:
                    fallback_models = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]
            
            if not is_flash:
                return original_generate_content(self, *args, **kwargs)
                
            last_ex = None
            for current_model in fallback_models:
                try:
                    if "model" in kwargs:
                        kwargs["model"] = current_model
                    else:
                        args = (current_model,) + args[1:]
                    
                    # Call the original method
                    return original_generate_content(self, *args, **kwargs)
                except Exception as e:
                    err_str = str(e).upper()
                    # Catch rate limits (429), quota, unavailable (503), or not found (404) errors
                    if any(x in err_str for x in ["429", "RESOURCE_EXHAUSTED", "QUOTA", "503", "UNAVAILABLE", "404", "NOT_FOUND"]):
                        # Add a short backoff delay to let the per-minute burst limit clear
                        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            import time
                            delay = 3.5
                            print(f"[ConceptRadar Fallback] Model '{current_model}' rate-limited. Pausing for {delay}s...")
                            time.sleep(delay)
                            
                        print(f"[ConceptRadar Fallback] Model '{current_model}' failed ({err_str.strip()}). Retrying with next model...")
                        last_ex = e
                        continue
                    else:
                        # Reraise other errors immediately (e.g. bad schema, bad prompt)
                        raise e
            
            print(f"[ConceptRadar Fallback] All preferred models failed. Raising error.")
            if last_ex:
                raise last_ex
            raise Exception("No fallback model succeeded.")

        google.genai.models.Models.generate_content = patched_generate_content
        print("[ConceptRadar Patches] Applied Models.generate_content fallback patch: SUCCESS.")

        # 2. Monkeypatch AsyncModels.generate_content for automatic model fallbacks (Async)
        original_generate_content_async = google.genai.models.AsyncModels.generate_content

        async def patched_generate_content_async(self, *args, **kwargs):
            model = kwargs.get("model")
            if not model and len(args) > 0:
                model = args[0]
                
            # Fallback list for standard flash models
            fallback_models = []
            is_flash = False
            if model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]:
                is_flash = True
                if model == "gemini-2.5-flash":
                    fallback_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]
                elif model == "gemini-2.0-flash":
                    fallback_models = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
                else:
                    fallback_models = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]
            
            if not is_flash:
                return await original_generate_content_async(self, *args, **kwargs)
                
            last_ex = None
            for current_model in fallback_models:
                try:
                    if "model" in kwargs:
                        kwargs["model"] = current_model
                    else:
                        args = (current_model,) + args[1:]
                    
                    # Call the original async method
                    return await original_generate_content_async(self, *args, **kwargs)
                except Exception as e:
                    err_str = str(e).upper()
                    # Catch rate limits (429), quota, unavailable (503), or not found (404) errors
                    if any(x in err_str for x in ["429", "RESOURCE_EXHAUSTED", "QUOTA", "503", "UNAVAILABLE", "404", "NOT_FOUND"]):
                        # Add a short backoff delay to let the per-minute burst limit clear
                        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            import asyncio
                            delay = 3.5
                            print(f"[ConceptRadar Fallback Async] Model '{current_model}' rate-limited. Pausing for {delay}s...")
                            await asyncio.sleep(delay)
                            
                        print(f"[ConceptRadar Fallback Async] Model '{current_model}' failed ({err_str.strip()}). Retrying with next model...")
                        last_ex = e
                        continue
                    else:
                        # Reraise other errors immediately (e.g. bad schema, bad prompt)
                        raise e
            
            print(f"[ConceptRadar Fallback Async] All preferred models failed. Raising error.")
            if last_ex:
                raise last_ex
            raise Exception("No fallback async model succeeded.")

        google.genai.models.AsyncModels.generate_content = patched_generate_content_async
        print("[ConceptRadar Patches] Applied AsyncModels.generate_content fallback patch: SUCCESS.")

    except Exception as ex:
        print(f"Failed to apply fallback monkeypatches: {ex}")
