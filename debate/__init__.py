from debate.admin import debate_admin_bp
from debate.config import argument_template_context
from debate.routes import debate_bp

debate_bp.context_processor(argument_template_context)
debate_admin_bp.context_processor(argument_template_context)

__all__ = ["debate_bp", "debate_admin_bp"]
