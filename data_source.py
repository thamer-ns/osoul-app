# data_source.py
TADAWUL_DB = {
    '1120': {'name': 'الراجحي', 'sector': 'البنوك'},
    '1180': {'name': 'الأهلي', 'sector': 'البنوك'},
    '2222': {'name': 'أرامكو', 'sector': 'الطاقة'},
    '2010': {'name': 'سابك', 'sector': 'المواد الأساسية'},
    '7010': {'name': 'STC', 'sector': 'الاتصالات'},
    '4190': {'name': 'جرير', 'sector': 'تجزئة'},
    '2280': {'name': 'المراعي', 'sector': 'أغذية'},
    '4263': {'name': 'سال', 'sector': 'نقل'},
    '4002': {'name': 'المواساة', 'sector': 'صحة'},
    '2082': {'name': 'أكوا باور', 'sector': 'مرافق'},
    '1150': {'name': 'الإنماء', 'sector': 'البنوك'},
    '1010': {'name': 'الرياض', 'sector': 'البنوك'},
    '7202': {'name': 'سلوشنز', 'sector': 'تقنية'},
    '7203': {'name': 'علم', 'sector': 'تقنية'}
    # أضف المزيد حسب حاجتك
}

def get_company_details(symbol):
    sym = str(symbol).replace('.0', '').strip()
    data = TADAWUL_DB.get(sym)
    if data: return data['name'], data['sector']
    return None, None
