"""Offline contract checks; real desktop model acceptance is a separate step."""
from pathlib import Path
import csv,hashlib,json,math,subprocess,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import svsettings
from svapi.runner import validate_recipe
from svapi.verify import verify_complex_fft

ROOT=Path(__file__).resolve().parents[1]


class Contract(unittest.TestCase):
    def test_helpers_are_exactly_the_declared_three(self):
        self.assertEqual(len(svsettings.helper_manifest()),3)

    def test_generic_recipes(self):
        for path in (ROOT/'recipes').glob('*.json'):
            validate_recipe(json.loads(path.read_text(encoding='utf-8')))

    def test_version_stdout_is_json(self):
        result=subprocess.run([sys.executable,str(ROOT/'sv.py'),'version'],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0)
        self.assertEqual(json.loads(result.stdout)['result']['version'],'0.1.0')

    def test_fft_checker_rejects_a_modified_bin(self):
        count=101;fs=1000
        y=[math.cos(2*math.pi*7*i/count) for i in range(count)]
        mag=[]
        for k in range(-count//2+1,count//2+1):
            re=sum(v*math.cos(2*math.pi*k*n/count) for n,v in enumerate(y))/fs
            im=sum(-v*math.sin(2*math.pi*k*n/count) for n,v in enumerate(y))/fs
            mag.append(math.hypot(re,im))
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);wave=temp/'wave.csv';fft=temp/'fft.csv'
            def write(path,x,y):
                with path.open('w',newline='',encoding='utf-8') as stream:
                    writer=csv.writer(stream);writer.writerow(['x','y']);writer.writerows(zip(x,y))
            write(wave,[i/fs for i in range(count)],y)
            frequencies=[(i-count//2)*fs/count for i in range(count)]
            write(fft,frequencies,mag)
            self.assertTrue(verify_complex_fft(wave,fft,fs)['passed'])
            mag[10]+=.01;write(fft,frequencies,mag)
            self.assertFalse(verify_complex_fft(wave,fft,fs)['passed'])

    def test_allowlist_has_no_user_artifact_formats(self):
        sys.path.insert(0,str(ROOT/'tools'))
        from package_release import FILES
        self.assertFalse(any(Path(name).suffix in ['.svu','.csv','.png','.wmf','.docx','.log','.pdb'] for name in FILES))


if __name__=='__main__':unittest.main()
