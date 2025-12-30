import zlib
import qrcode
from io import BytesIO
import base64

class PixGenerator:
    def __init__(self, chave_pix, beneficiario, cidade, valor=0.0):
        self.chave_pix = chave_pix
        self.beneficiario = beneficiario
        self.cidade = cidade
        self.valor = valor

    def _fix_size(self, text):
        return str(len(text)).zfill(2)

    def _crc16_ccitt(self, data):
        data = data.encode('utf-8')
        poly = 0x1021
        res = 0xFFFF
        for b in data:
            res ^= b << 8
            for _ in range(8):
                if res & 0x8000:
                    res = (res << 1) ^ poly
                else:
                    res = res << 1
                res &= 0xFFFF
        return hex(res).upper()[2:].zfill(4)

    def generate_payload(self):
        # Payload Format Indicator
        pfi = "000201"
        # Merchant Account Information
        gui = "0014br.gov.bcb.pix"
        key = f"01{self._fix_size(self.chave_pix)}{self.chave_pix}"
        mai = f"26{self._fix_size(gui + key)}{gui}{key}"
        # Merchant Category Code
        mcc = "52040000"
        # Transaction Currency (Real = 986)
        curr = "5303986"
        # Transaction Amount
        amt = f"54{self._fix_size(f'{self.valor:.2f}')}{self.valor:.2f}" if self.valor > 0 else ""
        # Country Code
        cc = "5802BR"
        # Merchant Name
        mn = f"59{self._fix_size(self.beneficiario)}{self.beneficiario}"
        # Merchant City
        mc = f"60{self._fix_size(self.cidade)}{self.cidade}"
        # Additional Data Field Template (ID do pedido opcional)
        adft = "62070503***"

        payload = f"{pfi}{mai}{mcc}{curr}{amt}{cc}{mn}{mc}{adft}6304"
        return f"{payload}{self._crc16_ccitt(payload)}"

    def generate_qr_base64(self):
        payload = self.generate_payload()
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode(), payload

if __name__ == "__main__":
    # Teste rápido
    pix = PixGenerator("test@pix.com", "JOAO SILVA", "SAO PAULO", 10.50)
    print(pix.generate_payload())
